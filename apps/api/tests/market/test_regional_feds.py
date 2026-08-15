from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.market.providers.base import DateRange, ProviderError
from app.market.providers.regional_feds import RegionalFedsProvider

ATLANTA_RSS = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0"><channel>
<item>
  <title>President Bostic Speaks at &lt;cite&gt;Farm Journal&lt;/cite&gt;'s Summit</title>
  <link>https://www.atlantafed.org/news/speeches/2026/02/02/bostic-rotary-club-atlanta</link>
  <pubDate>Mon, 2 Feb 2026 12:30:00 EST</pubDate>
</item>
<item>
  <title>Old speech, before the since cutoff</title>
  <link>https://www.atlantafed.org/news/speeches/2020/01/01/old</link>
  <pubDate>Wed, 1 Jan 2020 12:00:00 EST</pubDate>
</item>
</channel></rss>
"""


@respx.mock
async def test_news_parses_feed_and_filters_by_since(http_client: httpx.AsyncClient) -> None:
    respx.get("https://www.atlantafed.org/rss/speechindex").mock(
        return_value=httpx.Response(200, text=ATLANTA_RSS)
    )
    provider = RegionalFedsProvider(http_client)

    items = await provider.news([], since=datetime(2026, 1, 1, tzinfo=UTC))

    assert len(items) == 1  # the 2020 speech is filtered out by `since`
    speech = items[0]
    assert speech.source == "regional_feds"
    assert speech.topics == ["speech", "atl"]
    assert speech.headline == "President Bostic Speaks at Farm Journal's Summit"


@respx.mock
async def test_news_raises_on_http_error(http_client: httpx.AsyncClient) -> None:
    respx.get("https://www.atlantafed.org/rss/speechindex").mock(return_value=httpx.Response(500))
    provider = RegionalFedsProvider(http_client)

    with pytest.raises(ProviderError):
        await provider.news([], since=datetime(2026, 1, 1, tzinfo=UTC))


async def test_quote_candles_calendar_raise_not_implemented(http_client: httpx.AsyncClient) -> None:
    provider = RegionalFedsProvider(http_client)

    with pytest.raises(NotImplementedError):
        await provider.quote(["AAPL"])
    with pytest.raises(NotImplementedError):
        await provider.candles("AAPL", tf="1d", limit=10)
    with pytest.raises(NotImplementedError):
        await provider.calendar(
            DateRange(start=datetime.now(tz=UTC).date(), end=datetime.now(tz=UTC).date())
        )
