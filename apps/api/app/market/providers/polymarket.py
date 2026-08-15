import json
import re
from datetime import datetime

import httpx

from app.market.providers.base import ProviderError
from app.market.schemas import EarningsMarket, PredictionMarket

BASE_URL = "https://gamma-api.polymarket.com"

# Verified live (docs/DECISIONS.md ADR-0024): among Polymarket's top-volume
# markets, per-company earnings questions don't appear — its top-ranked
# finance/macro depth is Fed rate-decision markets and daily S&P direction,
# plus occasional treasury/inflation/jobs markets. This list is what
# actually matched real markets in that ranked feed, not aspirational —
# same "attach_to" keyword-match design sources.yaml already specified for
# the calendar. (Per-company earnings markets do exist on Polymarket, just
# on a separate low-per-market-volume feed — see earnings_calendar() below,
# ADR-0026 — this regex is deliberately still scoped to the ranked-by-volume
# macro feed, not earnings questions.)
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

# polymarket.com/earnings — a dedicated events feed (tag_slug=earnings),
# distinct from probability()'s ranked-by-volume /markets feed above. Each
# event is "Will <Company> (<TICKER>) beat quarterly earnings?", one market
# per event. ~40-100 live at a time (verified live 2026-08-15), comfortably
# under one page.
_EARNINGS_PAGE_SIZE = 500
_EARNINGS_QUESTION_RE = re.compile(r"^Will (.+?) \(([A-Z.]{1,6})\) beat quarterly earnings\?$")
_EPS_ESTIMATE_RE = re.compile(r"is (-?\$-?[\d,]+\.?\d*) as of market creation")


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

    async def earnings_calendar(self, limit: int = 100) -> list[EarningsMarket]:
        """polymarket.com/earnings — real per-company "beat consensus EPS"
        markets, one per event/`tag_slug=earnings`. Distinct feed from
        probability() above (docs/DECISIONS.md ADR-0026).
        """
        try:
            response = await self._client.get(
                f"{BASE_URL}/events",
                params={
                    "tag_slug": "earnings",
                    "closed": "false",
                    "limit": _EARNINGS_PAGE_SIZE,
                    "order": "endDate",
                    "ascending": "true",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"polymarket earnings request failed: {exc}") from exc
        events = response.json()
        if not isinstance(events, list):
            return []

        calendar: list[EarningsMarket] = []
        for event in events:
            markets = event.get("markets") if isinstance(event, dict) else None
            if not isinstance(markets, list) or not markets:
                continue
            market = markets[0]
            question = str(market.get("question") or "")
            match = _EARNINGS_QUESTION_RE.match(question)
            if not match:
                continue
            company, ticker = match.group(1), match.group(2)

            outcomes = _parse_json_list(market.get("outcomes"))
            prices = _parse_json_list(market.get("outcomePrices"))
            if not outcomes or not prices or len(outcomes) != len(prices):
                continue
            try:
                yes_index = outcomes.index("Yes")
                probability_pct = float(prices[yes_index]) * 100
            except (ValueError, IndexError):
                continue

            slug = event.get("slug") or market.get("slug")
            if not slug:
                continue

            report_date: datetime | None = None
            end_date_raw = market.get("endDate")
            if isinstance(end_date_raw, str):
                try:
                    report_date = datetime.fromisoformat(end_date_raw.replace("Z", "+00:00"))
                except ValueError:
                    pass

            eps_match = _EPS_ESTIMATE_RE.search(str(market.get("description") or ""))
            eps_estimate = eps_match.group(1) if eps_match else None

            # Unlike probability()'s /markets feed (volume24hr comes back as a
            # float), this /events feed returns volume as a numeric *string*
            # — verified live 2026-08-15. Handle both rather than assuming.
            volume_raw = market.get("volume")
            volume = 0.0
            if isinstance(volume_raw, int | float):
                volume = float(volume_raw)
            elif isinstance(volume_raw, str):
                try:
                    volume = float(volume_raw)
                except ValueError:
                    pass

            calendar.append(
                EarningsMarket(
                    ticker=ticker,
                    company=company,
                    eps_estimate=eps_estimate,
                    probability_pct=probability_pct,
                    volume=volume,
                    report_date=report_date,
                    url=f"https://polymarket.com/event/{slug}",
                )
            )

        # Real gaps: entries with no parseable report date sort last, not
        # dropped (docs/CLAUDE.md — never hide a real market, just be honest
        # about the missing field).
        calendar.sort(key=lambda m: (m.report_date is None, m.report_date))
        return calendar[:limit]
