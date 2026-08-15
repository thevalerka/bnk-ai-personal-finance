from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.market.providers.base import DateRange, ProviderError
from app.market.providers.federal_reserve import FederalReserveProvider

PRESS_RSS = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0"><channel>
<item>
  <title>Federal Reserve issues FOMC statement</title>
  <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm</link>
  <guid>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260729a.htm</guid>
  <pubDate>Wed, 29 Jul 2026 18:00:00 GMT</pubDate>
</item>
</channel></rss>
"""

SPEECHES_RSS = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0"><channel>
<item>
  <title>Cook, Outlook for the U.S. Economy</title>
  <link>https://www.federalreserve.gov/newsevents/speech/cook20260805a.htm</link>
  <guid>https://www.federalreserve.gov/newsevents/speech/cook20260805a.htm</guid>
  <pubDate>Wed, 5 Aug 2026 20:05:00 GMT</pubDate>
</item>
<item>
  <title>Old speech, before the since cutoff</title>
  <link>https://www.federalreserve.gov/newsevents/speech/old20200101a.htm</link>
  <guid>https://www.federalreserve.gov/newsevents/speech/old20200101a.htm</guid>
  <pubDate>Wed, 1 Jan 2020 12:00:00 GMT</pubDate>
</item>
</channel></rss>
"""


@respx.mock
async def test_news_parses_both_feeds_and_filters_by_since(http_client: httpx.AsyncClient) -> None:
    respx.get("https://www.federalreserve.gov/feeds/press_monetary.xml").mock(
        return_value=httpx.Response(200, text=PRESS_RSS)
    )
    respx.get("https://www.federalreserve.gov/feeds/speeches.xml").mock(
        return_value=httpx.Response(200, text=SPEECHES_RSS)
    )
    provider = FederalReserveProvider(http_client)

    items = await provider.news([], since=datetime(2026, 1, 1, tzinfo=UTC))

    assert len(items) == 2  # the 2020 speech is filtered out by `since`
    fomc = next(i for i in items if "FOMC" in i.headline)
    assert fomc.source == "federal_reserve"
    assert fomc.topics == ["fomc"]
    assert fomc.ts == datetime(2026, 7, 29, 18, 0, tzinfo=UTC)
    speech = next(i for i in items if "Cook" in i.headline)
    assert speech.topics == ["speech"]


@respx.mock
async def test_news_raises_on_http_error(http_client: httpx.AsyncClient) -> None:
    respx.get("https://www.federalreserve.gov/feeds/press_monetary.xml").mock(
        return_value=httpx.Response(500)
    )
    provider = FederalReserveProvider(http_client)

    with pytest.raises(ProviderError):
        await provider.news([], since=datetime(2026, 1, 1, tzinfo=UTC))


async def test_quote_candles_calendar_raise_not_implemented(http_client: httpx.AsyncClient) -> None:
    provider = FederalReserveProvider(http_client)

    with pytest.raises(NotImplementedError):
        await provider.quote(["AAPL"])
    with pytest.raises(NotImplementedError):
        await provider.candles("AAPL", tf="1d", limit=10)
    with pytest.raises(NotImplementedError):
        await provider.calendar(
            DateRange(start=datetime.now(tz=UTC).date(), end=datetime.now(tz=UTC).date())
        )
