from datetime import date, datetime

import httpx

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, FinancialPeriod, NewsItem, Quote

BASE_URL = "https://data.sec.gov"

# SEC 403s without a real contact string (docs/DECISIONS.md ADR-0019,
# matching sources.yaml's declared defaults.user_agent).
USER_AGENT = "AdaptiveMarketsTerminal/0.1 (+https://terminal.example.com; thevalerka@gmail.com)"

# Curated from the equity universe this app already tracks for real (Tape +
# Most Traded — apps/api/app/api/market.py TAPE_SPEC, apps/web/src/app/
# page.tsx MOST_TRADED_GROUPS), not a new aspirational universe — same
# precedent as config/taxonomy.yaml. SPY/QQQ/DIA/IWM excluded: they're ETFs
# and don't file 8-Ks the way an operating company does. CIKs resolved live
# from SEC's own company_tickers.json (docs/DECISIONS.md ADR-0019).
_COMPANIES = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "AMZN": "0001018724",
    "GOOGL": "0001652044",
    "META": "0001326801",
    "TSLA": "0001318605",
    "AMD": "0000002488",
    "PLTR": "0001321655",
    "SOFI": "0001818874",
}

# 8-K item -> plain-English label, for the headline. Not exhaustive — just
# the items sources.yaml calls out as high-signal plus a few common others.
# "9.01" (Financial Statements and Exhibits) is deliberately excluded: it's
# almost always a boilerplate companion item, not the newsworthy one.
_ITEM_LABELS = {
    "1.01": "Entry into a Material Definitive Agreement",
    "2.02": "Results of Operations and Financial Condition",
    "3.01": "Notice of Delisting or Failure to Satisfy a Listing Rule",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "5.02": "Departure/Election of Directors or Officers",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
}


def _label_for_items(items_str: str) -> str:
    codes = [c.strip() for c in items_str.split(",") if c.strip() and c.strip() != "9.01"]
    for code in codes:
        if code in _ITEM_LABELS:
            return _ITEM_LABELS[code]
    if codes:
        return f"Item {codes[0]}"
    return "Other Events"


# us-gaap XBRL concept names vary by company/era (verified live across all
# 10 curated tickers, docs/DECISIONS.md ADR-0022) — tried in order, first
# tag with data for a given period wins; a later tag only fills gaps the
# earlier one left. Some fields are genuinely absent for some companies
# (e.g. gross margin / SG&A for SOFI, a lender with no traditional
# cost-of-revenue structure, or Liabilities for a couple of others) — left
# null rather than computing/guessing a number that wouldn't mean the same
# thing for that business.
_REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]
_COST_OF_REVENUE_TAGS = ["CostOfRevenue", "CostOfGoodsAndServicesSold"]
_GROSS_PROFIT_TAGS = ["GrossProfit"]
_RESEARCH_DEVELOPMENT_TAGS = ["ResearchAndDevelopmentExpense"]
_SGA_TAGS = ["SellingGeneralAndAdministrativeExpense", "GeneralAndAdministrativeExpense"]
_OPERATING_EXPENSES_TAGS = ["OperatingExpenses"]
_OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]
_INTEREST_EXPENSE_TAGS = ["InterestExpense"]
_INCOME_TAX_TAGS = ["IncomeTaxExpenseBenefit"]
_NET_INCOME_TAGS = ["NetIncomeLoss"]
_EPS_DILUTED_TAGS = ["EarningsPerShareDiluted"]
_EPS_BASIC_TAGS = ["EarningsPerShareBasic"]
_OPERATING_CASH_FLOW_TAGS = ["NetCashProvidedByUsedInOperatingActivities"]
_CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]

# Balance-sheet concepts are "instant" (point-in-time) XBRL facts — no
# `start`/duration, just a snapshot as of `end` — looked up directly against
# the period-end dates already chosen from the income-statement figures
# above, not span-filtered the same way.
_ASSETS_TAGS = ["Assets"]
_LIABILITIES_TAGS = ["Liabilities"]
_STOCKHOLDERS_EQUITY_TAGS = ["StockholdersEquity"]
_CASH_TAGS = ["CashAndCashEquivalentsAtCarryingValue"]
_LONG_TERM_DEBT_TAGS = ["LongTermDebtNoncurrent", "LongTermDebt"]

# Day-span of (end - start) that identifies a genuine single fiscal-year or
# single-quarter figure — a 10-Q's XBRL facts also carry a year-to-date
# cumulative value under the same tag, which these ranges exclude.
_ANNUAL_SPAN = (350, 380)
_QUARTERLY_SPAN = (80, 100)


def _duration_values(
    gaap: dict[str, object], tags: list[str], span_range: tuple[int, int], unit: str = "USD"
) -> dict[str, tuple[float, str]]:
    """`end` -> (val, fiscal_period) for the first tag with data, restricted
    to facts whose (end - start) falls in `span_range` (see module docstring
    above) and keeping the most-recently-`filed` value per `end` (a value
    gets re-reported as a restated comparative in later filings; the latest
    filing's figure is the most authoritative).
    """
    result: dict[str, tuple[float, str]] = {}
    for tag in tags:
        concept = gaap.get(tag)
        if not isinstance(concept, dict):
            continue
        per_tag: dict[str, tuple[str, float, str]] = {}
        for row in concept.get("units", {}).get(unit, []):
            form = str(row.get("form", ""))
            if not (form.startswith("10-K") or form.startswith("10-Q")):
                continue
            try:
                start = date.fromisoformat(row["start"])
                end = date.fromisoformat(row["end"])
                val = float(row["val"])
                filed = str(row["filed"])
                fp = str(row.get("fp", ""))
            except (KeyError, ValueError, TypeError):
                continue
            if not (span_range[0] <= (end - start).days <= span_range[1]):
                continue
            key = row["end"]
            if key not in per_tag or filed > per_tag[key][0]:
                per_tag[key] = (filed, val, fp)
        for key, (_filed, val, fp) in per_tag.items():
            result.setdefault(key, (val, fp))
    return result


def _instant_values(
    gaap: dict[str, object], tags: list[str], wanted_ends: set[str], unit: str = "USD"
) -> dict[str, float]:
    """`end` -> val for a point-in-time (balance-sheet) concept, restricted
    to the exact period-end dates already selected elsewhere.
    """
    result: dict[str, float] = {}
    for tag in tags:
        concept = gaap.get(tag)
        if not isinstance(concept, dict):
            continue
        per_tag: dict[str, tuple[str, float]] = {}
        for row in concept.get("units", {}).get(unit, []):
            end = row.get("end")
            if end not in wanted_ends:
                continue
            form = str(row.get("form", ""))
            if not (form.startswith("10-K") or form.startswith("10-Q")):
                continue
            try:
                val = float(row["val"])
                filed = str(row["filed"])
            except (KeyError, ValueError, TypeError):
                continue
            if end not in per_tag or filed > per_tag[end][0]:
                per_tag[end] = (filed, val)
        for end, (_filed, val) in per_tag.items():
            result.setdefault(end, val)
    return result


def _at(values: dict[str, tuple[float, str]], key: str) -> float | None:
    entry = values.get(key)
    return entry[0] if entry else None


class SecEdgarProvider:
    """8-K material-event filings and annual financial statement figures for
    a curated set of tickers, straight from EDGAR — the highest
    signal-to-noise "news" source that exists, and it's free (SOURCES.md).
    `news()` is merged into the news capability chain alongside equity_news/
    macro_news/regional_fed_news, not a fallback for any of them
    (config/providers.yaml); `fundamentals()` is called directly by the
    stock detail endpoint (docs/DECISIONS.md ADR-0021).
    """

    name = "sec_edgar"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._headers = {"User-Agent": USER_AGENT}

    async def quote(self, symbols: list[str]) -> list[Quote]:
        raise NotImplementedError("sec_edgar is a filings source, not quotes")

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        raise NotImplementedError("sec_edgar is a filings source, not candles")

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        # Scoped to just the requested ticker(s) when given (a stock detail
        # page asking for one company's filings) — falls back to every
        # curated ticker when topics is empty (the merged /market/news feed).
        wanted = (
            [t.upper() for t in topics if t.upper() in _COMPANIES] if topics else list(_COMPANIES)
        )
        items: list[NewsItem] = []
        for ticker in wanted:
            cik = _COMPANIES[ticker]
            try:
                response = await self._client.get(
                    f"{BASE_URL}/submissions/CIK{cik}.json", headers=self._headers
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"sec_edgar request failed for {ticker}: {exc}") from exc
            recent = response.json().get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            for i, form in enumerate(forms):
                if form != "8-K":
                    continue
                ts = datetime.fromisoformat(recent["acceptanceDateTime"][i])
                if ts < since:
                    continue
                accession = recent["accessionNumber"][i]
                accession_nodash = accession.replace("-", "")
                doc = recent["primaryDocument"][i]
                label = _label_for_items(recent.get("items", [""] * len(forms))[i])
                items.append(
                    NewsItem(
                        id=accession,
                        ts=ts,
                        headline=f"{ticker} 8-K — {label}",
                        url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{doc}",
                        source=self.name,
                        tickers=[ticker],
                        topics=["filing", "8-K"],
                    )
                )
        return items

    async def fundamentals(
        self, ticker: str, annual_limit: int = 5, quarterly_limit: int = 8
    ) -> list[FinancialPeriod]:
        """Last `annual_limit` fiscal years (10-K) and `quarterly_limit`
        quarters (10-Q) of financial-statement figures, from EDGAR's XBRL
        company-facts endpoint — not part of the Provider Protocol (quote/
        candles/news/calendar don't fit structured financial data), called
        directly rather than through the Router (docs/DECISIONS.md
        ADR-0021/0022). Sorted newest-first, annual and quarterly periods
        interleaved by date (their end dates never collide in practice).
        """
        ticker = ticker.upper()
        if ticker not in _COMPANIES:
            return []
        cik = _COMPANIES[ticker]
        try:
            response = await self._client.get(
                f"{BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json", headers=self._headers
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"sec_edgar fundamentals request failed for {ticker}: {exc}"
            ) from exc

        gaap = response.json().get("facts", {}).get("us-gaap", {})
        periods: list[FinancialPeriod] = []

        for span_range, form, limit in (
            (_ANNUAL_SPAN, "10-K", annual_limit),
            (_QUARTERLY_SPAN, "10-Q", quarterly_limit),
        ):
            revenue = _duration_values(gaap, _REVENUE_TAGS, span_range)
            if not revenue:
                continue
            cost_of_revenue = _duration_values(gaap, _COST_OF_REVENUE_TAGS, span_range)
            gross_profit = _duration_values(gaap, _GROSS_PROFIT_TAGS, span_range)
            research_development = _duration_values(gaap, _RESEARCH_DEVELOPMENT_TAGS, span_range)
            sga = _duration_values(gaap, _SGA_TAGS, span_range)
            operating_expenses = _duration_values(gaap, _OPERATING_EXPENSES_TAGS, span_range)
            operating_income = _duration_values(gaap, _OPERATING_INCOME_TAGS, span_range)
            interest_expense = _duration_values(gaap, _INTEREST_EXPENSE_TAGS, span_range)
            income_tax = _duration_values(gaap, _INCOME_TAX_TAGS, span_range)
            net_income = _duration_values(gaap, _NET_INCOME_TAGS, span_range)
            eps_diluted = _duration_values(gaap, _EPS_DILUTED_TAGS, span_range, unit="USD/shares")
            eps_basic = _duration_values(gaap, _EPS_BASIC_TAGS, span_range, unit="USD/shares")
            operating_cash_flow = _duration_values(gaap, _OPERATING_CASH_FLOW_TAGS, span_range)
            capex = _duration_values(gaap, _CAPEX_TAGS, span_range)

            ends = sorted(revenue.keys(), reverse=True)[:limit]
            wanted_ends = set(ends)
            assets = _instant_values(gaap, _ASSETS_TAGS, wanted_ends)
            liabilities = _instant_values(gaap, _LIABILITIES_TAGS, wanted_ends)
            equity = _instant_values(gaap, _STOCKHOLDERS_EQUITY_TAGS, wanted_ends)
            cash = _instant_values(gaap, _CASH_TAGS, wanted_ends)
            long_term_debt = _instant_values(gaap, _LONG_TERM_DEBT_TAGS, wanted_ends)

            for end in ends:
                rev, fp = revenue[end]
                gp = _at(gross_profit, end)
                cor = _at(cost_of_revenue, end)
                if gp is None and rev is not None and cor is not None:
                    gp = rev - cor
                oi = _at(operating_income, end)
                ni = _at(net_income, end)
                ocf = _at(operating_cash_flow, end)
                capex_val = _at(capex, end)
                fcf = (ocf - capex_val) if ocf is not None and capex_val is not None else None
                periods.append(
                    FinancialPeriod(
                        period_end=date.fromisoformat(end),
                        fiscal_period=fp,
                        form=form,
                        revenue=rev,
                        cost_of_revenue=cor,
                        gross_profit=gp,
                        gross_margin_pct=(gp / rev * 100) if gp is not None and rev else None,
                        research_development=_at(research_development, end),
                        sga_expense=_at(sga, end),
                        operating_expenses=_at(operating_expenses, end),
                        operating_income=oi,
                        operating_margin_pct=(oi / rev * 100) if oi is not None and rev else None,
                        interest_expense=_at(interest_expense, end),
                        income_tax_expense=_at(income_tax, end),
                        net_income=ni,
                        net_margin_pct=(ni / rev * 100) if ni is not None and rev else None,
                        eps_diluted=_at(eps_diluted, end),
                        eps_basic=_at(eps_basic, end),
                        operating_cash_flow=ocf,
                        capex=capex_val,
                        free_cash_flow=fcf,
                        total_assets=assets.get(end),
                        total_liabilities=liabilities.get(end),
                        stockholders_equity=equity.get(end),
                        cash_and_equivalents=cash.get(end),
                        long_term_debt=long_term_debt.get(end),
                    )
                )

        periods.sort(key=lambda p: p.period_end, reverse=True)
        return periods

    async def calendar(self, window: DateRange) -> list[Event]:
        raise NotImplementedError(
            "sec_edgar filings are already-happened disclosures, not scheduled events"
        )

    def cost(self, call: CallSpec) -> int:
        wanted = [s for s in call.symbols if s.upper() in _COMPANIES]
        return len(wanted) if wanted else len(_COMPANIES)
