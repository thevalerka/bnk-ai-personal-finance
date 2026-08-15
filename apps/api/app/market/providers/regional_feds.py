import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

# Regional Fed president speeches, straight from each bank's own RSS feed —
# keyless, same primary-source rationale as federal_reserve.py. sources.yaml
# listed five banks (ny/sf/chi/atl/stl); only Atlanta's held up when probed
# live (docs/DECISIONS.md ADR-0018): NY and St. Louis's declared URLs 404,
# and Chicago's "Speeches" feed is stale and mislabeled (its actual content
# is 2022-2023 CFNAI index releases, not speeches). SF Fed's /feed/ works
# but is their general blog, not a speeches feed — mixing that in under a
# "speech" topic would misrepresent most of its content, so it's left out
# rather than guessed at. Dict-shaped so a bank can be added back the moment
# its feed is fixed and re-verified.
_FEEDS = {
    "atl": "https://www.atlantafed.org/rss/speechindex",
}

# Atlanta Fed's titles carry embedded markup (e.g. "...at <cite>Farm
# Journal</cite>'s Top Producer Summit", verified live) — stripped so a
# rendered headline doesn't show raw angle brackets as literal text.
_TAG_RE = re.compile(r"<[^>]+>")


class RegionalFedsProvider:
    """Regional Federal Reserve Bank president speeches — the same
    primary-source-over-aggregator argument as FederalReserveProvider,
    scoped to whichever regional banks actually publish a working RSS feed
    (docs/DECISIONS.md ADR-0018). Merged into news alongside equity_news/
    macro_news, not a fallback for either (config/providers.yaml).
    """

    name = "regional_feds"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def quote(self, symbols: list[str]) -> list[Quote]:
        raise NotImplementedError("regional_feds is a news source, not quotes")

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        raise NotImplementedError("regional_feds is a news source, not candles")

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        items: list[NewsItem] = []
        for bank_id, url in _FEEDS.items():
            try:
                response = await self._client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"regional_feds request failed: {exc}") from exc
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
                        headline=_TAG_RE.sub("", title).strip(),
                        url=link.strip(),
                        source=self.name,
                        topics=["speech", bank_id],
                    )
                )
        return items

    async def calendar(self, window: DateRange) -> list[Event]:
        raise NotImplementedError("regional_feds has no calendar-worthy content, only speeches")

    def cost(self, call: CallSpec) -> int:
        return len(_FEEDS)
