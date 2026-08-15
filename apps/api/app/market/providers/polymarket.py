import json
import re
from datetime import datetime

import httpx

from app.market.providers.base import ProviderError
from app.market.schemas import PredictionMarket

BASE_URL = "https://gamma-api.polymarket.com"

# Verified live (docs/DECISIONS.md ADR-0024): Polymarket has no meaningful
# per-company earnings markets at any real volume — its genuine finance/
# macro depth is Fed rate-decision markets and daily S&P direction, plus
# occasional treasury/inflation/jobs markets. This list is what actually
# matched real markets when checked, not aspirational — same "attach_to"
# keyword-match design sources.yaml already specified for the calendar.
_KEYWORDS_RE = re.compile(
    r"fed |fomc|interest rate|inflation|\bcpi\b|jobs report|nonfarm|payroll|"
    r"unemployment|\bgdp\b|recession|s&p 500|nasdaq|dow jones|treasury yield",
    re.IGNORECASE,
)

# Gamma API caps a single page at 100 markets; 3 pages sorted by 24h volume
# is enough to reach real but lower-volume macro markets without an
# unbounded number of requests per call.
_PAGE_SIZE = 100
_PAGE_OFFSETS = (0, 100, 200)


def _parse_json_list(value: object) -> list[str] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


class PolymarketProvider:
    """Market-implied probability for finance/macro-relevant real-money
    prediction markets — keyless, real-time. Not part of the Provider
    Protocol (probability doesn't fit quote/candles/news/calendar), called
    directly rather than through the Router (docs/DECISIONS.md ADR-0024).
    """

    name = "polymarket"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def probability(self, limit: int = 12) -> list[PredictionMarket]:
        markets: list[dict[str, object]] = []
        for offset in _PAGE_OFFSETS:
            try:
                response = await self._client.get(
                    f"{BASE_URL}/markets",
                    params={
                        "limit": _PAGE_SIZE,
                        "offset": offset,
                        "active": "true",
                        "closed": "false",
                        "order": "volume24hr",
                        "ascending": "false",
                    },
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"polymarket request failed: {exc}") from exc
            page = response.json()
            if not isinstance(page, list) or not page:
                break
            markets.extend(page)

        matched: list[PredictionMarket] = []
        seen_questions: set[str] = set()
        for market in markets:
            question = str(market.get("question") or "")
            if not question or question in seen_questions or not _KEYWORDS_RE.search(question):
                continue
            outcomes = _parse_json_list(market.get("outcomes"))
            prices = _parse_json_list(market.get("outcomePrices"))
            if not outcomes or not prices or len(outcomes) != len(prices):
                continue
            try:
                yes_index = outcomes.index("Yes")
                probability_pct = float(prices[yes_index]) * 100
            except (ValueError, IndexError):
                continue

            events = market.get("events")
            event_slug = None
            if isinstance(events, list) and events and isinstance(events[0], dict):
                event_slug = events[0].get("slug")
            slug = event_slug or market.get("slug")
            if not slug:
                continue

            end_date: datetime | None = None
            end_date_raw = market.get("endDate")
            if isinstance(end_date_raw, str):
                try:
                    end_date = datetime.fromisoformat(end_date_raw.replace("Z", "+00:00"))
                except ValueError:
                    pass

            volume_raw = market.get("volume24hr")
            volume_24h = float(volume_raw) if isinstance(volume_raw, int | float) else 0.0

            seen_questions.add(question)
            matched.append(
                PredictionMarket(
                    question=question,
                    probability_pct=probability_pct,
                    volume_24h=volume_24h,
                    end_date=end_date,
                    url=f"https://polymarket.com/event/{slug}",
                )
            )

        matched.sort(key=lambda m: m.volume_24h, reverse=True)
        return matched[:limit]
