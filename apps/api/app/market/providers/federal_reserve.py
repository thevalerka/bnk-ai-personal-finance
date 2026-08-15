from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

BASE_URL = "https://www.federalreserve.gov/feeds"

# Plain stdlib XML parsing, not a feed-parsing dependency: these are
# ordinary RSS 2.0 (verified live against the real feeds, docs/DECISIONS.md
# ADR-0017), and the whole item shape needed is title/link/guid/pubDate —
# not worth a new dependency for.
_FEEDS = {
    "press_monetary.xml": "fomc",
    "speeches.xml": "speech",
}


class FederalReserveProvider:
    """FOMC statements and Fed-official speeches, straight from the source
    (keyless RSS) — the primary-source counterpart to Finnhub's aggregated
    market news, not a replacement for it (config/providers.yaml keeps both
    in the equity_news/macro_news chains, merged not fallback).
    """

    name = "federal_reserve"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def quote(self, symbols: list[str]) -> list[Quote]:
        raise NotImplementedError("federal_reserve is a news source, not quotes")

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        raise NotImplementedError("federal_reserve is a news source, not candles")

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        items: list[NewsItem] = []
        for feed, topic in _FEEDS.items():
            try:
                response = await self._client.get(f"{BASE_URL}/{feed}")
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"federal_reserve request failed: {exc}") from exc
            root = ElementTree.fromstring(response.text)
            for item in root.iter("item"):
                pub_date = item.findtext("pubDate")
                link = item.findtext("link")
                title = item.findtext("title")
                if pub_date is None or link is None or title is None:
                    continue
                ts = parsedate_to_datetime(pub_date)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                if ts < since:
                    continue
                items.append(
                    NewsItem(
                        id=link,
                        ts=ts,
                        headline=title.strip(),
                        url=link.strip(),
                        source=self.name,
                        topics=[topic],
                    )
                )
        return items

    async def calendar(self, window: DateRange) -> list[Event]:
        raise NotImplementedError(
            "federal_reserve's calendar-worthy content (FOMC dates) requires "
            "scraping an HTML page (fomccalendars.htm), not an RSS/JSON "
            "endpoint — deferred, see docs/DECISIONS.md ADR-0017"
        )

    def cost(self, call: CallSpec) -> int:
        return len(_FEEDS)
