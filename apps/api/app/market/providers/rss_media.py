from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

# Keyless, breadth-over-precision market news RSS — headline+link only, per
# sources.yaml's licensing note ("headline + link only... never store or
# render full article bodies"). Both verified live (docs/DECISIONS.md
# ADR-0023). sources.yaml also lists a per-symbol Yahoo Finance feed
# (`per_symbol: true`) — deliberately not included here since this provider
# is a single flat news() call with no symbol parameter to template into a
# per-ticker URL; a per-symbol variant is a stock-detail-page feature, not
# a fit for the merged /market/news chain.
_FEEDS = {
    "cnbc_markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "marketwatch_top": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
}


class RssMediaProvider:
    """Cheap-breadth market news from major outlets' own RSS feeds — no key,
    no paid tier, headline+link only (sources.yaml licensing). Merged into
    the news capability chain alongside equity_news/macro_news/
    regional_fed_news/sec_filings_news, not a fallback for any of them
    (config/providers.yaml, docs/DECISIONS.md ADR-0023).
    """

    name = "rss_media"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def quote(self, symbols: list[str]) -> list[Quote]:
        raise NotImplementedError("rss_media is a news source, not quotes")

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        raise NotImplementedError("rss_media is a news source, not candles")

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        items: list[NewsItem] = []
        for feed_id, url in _FEEDS.items():
            try:
                response = await self._client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"rss_media request failed for {feed_id}: {exc}") from exc
            root = ElementTree.fromstring(response.text)
            for item in root.iter("item"):
                pub_date = item.findtext("pubDate")
                link = item.findtext("link")
                title = item.findtext("title")
                if pub_date is None or link is None or title is None:
                    continue
                try:
                    ts = parsedate_to_datetime(pub_date)
                except (TypeError, ValueError):
                    continue
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
                        topics=[feed_id],
                    )
                )
        return items

    async def calendar(self, window: DateRange) -> list[Event]:
        raise NotImplementedError("rss_media has no calendar-worthy content, only news")

    def cost(self, call: CallSpec) -> int:
        return len(_FEEDS)
