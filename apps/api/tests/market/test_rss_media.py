from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.market.providers.base import DateRange, ProviderError
from app.market.providers.rss_media import RssMediaProvider

CNBC_RSS = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0"><channel>
<item>
  <title>Wholesale prices were flat in July</title>
  <link>https://www.cnbc.com/2026/08/13/wholesale-prices.html</link>
  <pubDate>Thu, 13 Aug 2026 13:18:36 GMT</pubDate>
</item>
<item>
  <title>Old story, before the since cutoff</title>
  <link>https://www.cnbc.com/2020/01/01/old.html</link>
  <pubDate>Wed, 1 Jan 2020 12:00:00 GMT</pubDate>
</item>
</channel></rss>
"""

MARKETWATCH_RSS = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0"><channel>
<item>
  <title>Still trying to time the stock market?</title>
  <link>https://www.marketwatch.com/story/timing-the-market</link>
  <pubDate>Fri, 14 Aug 2026 16:21:00 GMT</pubDate>
</item>
</channel></rss>
"""


@respx.mock
async def test_news_parses_both_feeds_and_filters_by_since(http_client: httpx.AsyncClient) -> None:
    respx.get(
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"
    ).mock(return_value=httpx.Response(200, text=CNBC_RSS))
    respx.get("https://feeds.content.dowjones.io/public/rss/mw_topstories").mock(
        return_value=httpx.Response(200, text=MARKETWATCH_RSS)
    )
    provider = RssMediaProvider(http_client)

    items = await provider.news([], since=datetime(2026, 1, 1, tzinfo=UTC))

    assert len(items) == 2  # the 2020 CNBC story is filtered out by `since`
    cnbc = next(i for i in items if "Wholesale" in i.headline)
    assert cnbc.source == "rss_media"
    assert cnbc.topics == ["cnbc_markets"]
    marketwatch = next(i for i in items if "market" in i.headline.lower())
    assert marketwatch.topics == ["marketwatch_top"]


@respx.mock
async def test_news_raises_on_http_error(http_client: httpx.AsyncClient) -> None:
    respx.get(
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"
    ).mock(return_value=httpx.Response(500))
    provider = RssMediaProvider(http_client)

    with pytest.raises(ProviderError):
        await provider.news([], since=datetime(2026, 1, 1, tzinfo=UTC))


async def test_quote_candles_calendar_raise_not_implemented(http_client: httpx.AsyncClient) -> None:
    provider = RssMediaProvider(http_client)

    with pytest.raises(NotImplementedError):
        await provider.quote(["AAPL"])
    with pytest.raises(NotImplementedError):
        await provider.candles("AAPL", tf="1d", limit=10)
    with pytest.raises(NotImplementedError):
        await provider.calendar(
            DateRange(start=datetime.now(tz=UTC).date(), end=datetime.now(tz=UTC).date())
        )
