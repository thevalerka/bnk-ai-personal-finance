from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from app.market.providers.base import DateRange, ProviderError
from app.market.providers.sec_edgar import SecEdgarProvider
from tests.market.conftest import load_fixture


@respx.mock
async def test_news_parses_8ks_filters_form_and_since(http_client: httpx.AsyncClient) -> None:
    respx.route(url__regex=r"^https://data\.sec\.gov/submissions/CIK\d{10}\.json$").mock(
        return_value=httpx.Response(200, json=load_fixture("sec_edgar_submissions.json"))
    )
    provider = SecEdgarProvider(http_client)

    items = await provider.news([], since=datetime(2026, 1, 1, tzinfo=UTC))

    # One matching 8-K per ticker (the 2025 8-K is filtered by `since`, the
    # 10-K is filtered by form) — 10 tickers in the curated universe.
    assert len(items) == 10
    item = next(i for i in items if i.tickers == ["AAPL"])
    assert item.source == "sec_edgar"
    assert item.headline == "AAPL 8-K — Results of Operations and Financial Condition"
    assert item.id == "0000320193-26-000018"
    assert item.url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/filing-20260730.htm"
    )
    assert item.topics == ["filing", "8-K"]


@respx.mock
async def test_news_scopes_to_requested_ticker_when_topics_given(
    http_client: httpx.AsyncClient,
) -> None:
    route = respx.route(url__regex=r"^https://data\.sec\.gov/submissions/CIK\d{10}\.json$").mock(
        return_value=httpx.Response(200, json=load_fixture("sec_edgar_submissions.json"))
    )
    provider = SecEdgarProvider(http_client)

    items = await provider.news(["aapl"], since=datetime(2026, 1, 1, tzinfo=UTC))

    assert len(items) == 1
    assert items[0].tickers == ["AAPL"]
    assert route.call_count == 1  # only AAPL's CIK fetched, not all 10


@respx.mock
async def test_news_raises_on_http_error(http_client: httpx.AsyncClient) -> None:
    respx.route(url__regex=r"^https://data\.sec\.gov/submissions/CIK\d{10}\.json$").mock(
        return_value=httpx.Response(500)
    )
    provider = SecEdgarProvider(http_client)

    with pytest.raises(ProviderError):
        await provider.news([], since=datetime(2026, 1, 1, tzinfo=UTC))


@respx.mock
async def test_fundamentals_parses_annual_figures_and_computes_margins(
    http_client: httpx.AsyncClient,
) -> None:
    respx.route(url__regex=r"^https://data\.sec\.gov/api/xbrl/companyfacts/CIK\d{10}\.json$").mock(
        return_value=httpx.Response(200, json=load_fixture("sec_edgar_companyfacts.json"))
    )
    provider = SecEdgarProvider(http_client)

    periods = await provider.fundamentals("aapl")

    # 2 annual (10-K) periods + 1 quarterly (10-Q) period, sorted newest
    # first by period_end — the quarterly period (2025-06-28) sorts between
    # the two annual ones (2025-09-27 and 2024-09-28).
    assert len(periods) == 3
    latest, quarterly, prior = periods[0], periods[1], periods[2]

    assert latest.period_end == date(2025, 9, 27)
    assert latest.form == "10-K"
    assert latest.fiscal_period == "FY"
    assert latest.revenue == 416161000000
    assert latest.gross_profit == 195201000000
    assert latest.gross_margin_pct == pytest.approx(195201000000 / 416161000000 * 100)
    assert latest.operating_margin_pct == pytest.approx(133050000000 / 416161000000 * 100)
    assert latest.net_margin_pct == pytest.approx(112010000000 / 416161000000 * 100)
    assert latest.eps_diluted == 7.24
    assert latest.operating_cash_flow == 125000000000
    assert latest.capex == 11000000000
    assert latest.free_cash_flow == 125000000000 - 11000000000
    assert latest.total_assets == 359241000000  # instant fact, looked up by period_end

    # 2024-09-28 appears twice in the fixture (391000000000 filed 2024-11-01,
    # then restated to 391035000000 in the later 2025-10-31 filing) — the
    # more-recently-filed value should win.
    assert prior.period_end == date(2024, 9, 28)
    assert prior.revenue == 391035000000
    assert prior.eps_diluted == 6.08
    assert prior.total_assets == 364980000000
    # Not in the fixture for this period — stays null, not fabricated.
    assert prior.operating_cash_flow is None

    assert quarterly.period_end == date(2025, 6, 28)
    assert quarterly.form == "10-Q"
    assert quarterly.fiscal_period == "Q3"
    assert quarterly.revenue == 94036000000


@respx.mock
async def test_fundamentals_computes_gross_profit_when_not_reported_directly(
    http_client: httpx.AsyncClient,
) -> None:
    # Some companies (e.g. lenders) don't report a GrossProfit tag at all —
    # falls back to Revenue - CostOfRevenue rather than leaving it null.
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 1000.0,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-01",
                            }
                        ]
                    }
                },
                "CostOfRevenue": {
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 400.0,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-01",
                            }
                        ]
                    }
                },
            }
        }
    }
    respx.route(url__regex=r"^https://data\.sec\.gov/api/xbrl/companyfacts/CIK\d{10}\.json$").mock(
        return_value=httpx.Response(200, json=facts)
    )
    provider = SecEdgarProvider(http_client)

    periods = await provider.fundamentals("SOFI")

    assert len(periods) == 1
    assert periods[0].gross_profit == 600.0
    assert periods[0].gross_margin_pct == pytest.approx(60.0)
    assert periods[0].operating_income is None  # not reported in this fixture, stays null


async def test_fundamentals_returns_empty_for_a_ticker_outside_the_curated_set(
    http_client: httpx.AsyncClient,
) -> None:
    provider = SecEdgarProvider(http_client)

    periods = await provider.fundamentals("JPM")

    assert periods == []


@respx.mock
async def test_fundamentals_raises_on_http_error(http_client: httpx.AsyncClient) -> None:
    respx.route(url__regex=r"^https://data\.sec\.gov/api/xbrl/companyfacts/CIK\d{10}\.json$").mock(
        return_value=httpx.Response(500)
    )
    provider = SecEdgarProvider(http_client)

    with pytest.raises(ProviderError):
        await provider.fundamentals("AAPL")


async def test_quote_candles_calendar_raise_not_implemented(http_client: httpx.AsyncClient) -> None:
    provider = SecEdgarProvider(http_client)

    with pytest.raises(NotImplementedError):
        await provider.quote(["AAPL"])
    with pytest.raises(NotImplementedError):
        await provider.candles("AAPL", tf="1d", limit=10)
    with pytest.raises(NotImplementedError):
        await provider.calendar(DateRange(start=date(2026, 8, 14), end=date(2026, 9, 14)))
