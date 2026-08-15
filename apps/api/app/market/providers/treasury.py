from datetime import UTC, datetime

import httpx

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

BASE_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"


class TreasuryProvider:
    """US Treasury auction schedule (Treasury FiscalData). Keyless, no rate limit
    published — `defaults.budget_safety_factor` in the sources doc still applies,
    see config/budgets.yaml.

    Auction *results* are historical; this provider only surfaces the forward-
    looking `auction_date` rows within the requested window — that's the actual
    "auction schedule" calendar (docs/DECISIONS.md ADR-0017), not a market number,
    so it's calendar-only, not quote/candles.
    """

    name = "treasury"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def quote(self, symbols: list[str]) -> list[Quote]:
        raise NotImplementedError("treasury is a calendar source, not quotes")

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        raise NotImplementedError("treasury is a calendar source, not candles")

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        raise NotImplementedError("treasury has no news feed")

    async def calendar(self, window: DateRange) -> list[Event]:
        try:
            response = await self._client.get(
                f"{BASE_URL}/v1/accounting/od/auctions_query",
                params={
                    "filter": f"auction_date:gte:{window.start.isoformat()},"
                    f"auction_date:lte:{window.end.isoformat()}",
                    "sort": "auction_date",
                    "fields": "security_type,security_term,auction_date,cusip",
                    "page[size]": 100,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"treasury request failed: {exc}") from exc
        events = []
        for row in response.json().get("data", []):
            events.append(
                Event(
                    ts=datetime.fromisoformat(row["auction_date"]).replace(tzinfo=UTC),
                    kind="auction",
                    importance=1,
                    title=f"{row['security_term']} {row['security_type']} auction",
                    source=self.name,
                    tickers=[row["cusip"]],
                )
            )
        return events

    def cost(self, call: CallSpec) -> int:
        return 1
