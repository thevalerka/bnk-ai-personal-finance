"""Curated xStocks symbol list (docs/DECISIONS.md ADR-0029).

Jupiter/Backed Finance publish no canonical machine-readable registry of
xStocks mint addresses (verified via research before writing this — see
ADR-0029), so this is a symbol/name/category seed list, not a source of
truth for prices or mints. `app/jupiter/gateway.py` resolves each symbol to
a real mint + live price via Jupiter's own token search API at request
time (cached), and silently omits any symbol that doesn't resolve to a
verified token — never falls back to a hardcoded price or a guessed mint
(CLAUDE.md: no number without a real provider response behind it).

Two entries are genuinely pre-IPO/private exposure, not already-listed
equities — flagged `category="pre_ipo"` so the UI can disclose the
structural difference: VCXx wraps Fundrise's public "VCX" fund, which
itself holds private stakes (SpaceX, OpenAI, Anthropic, Databricks); SPCXx
is a direct synthetic SpaceX tracker. Neither confers shareholder rights,
same disclosure that applies to every xStock (price-exposure only).
"""

from typing import Literal

Category = Literal["public_equity", "pre_ipo"]

CATALOG: list[tuple[str, str, Category]] = [
    ("AAPLx", "Apple", "public_equity"),
    ("TSLAx", "Tesla", "public_equity"),
    ("NVDAx", "NVIDIA", "public_equity"),
    ("MSFTx", "Microsoft", "public_equity"),
    ("GOOGLx", "Alphabet", "public_equity"),
    ("AMZNx", "Amazon", "public_equity"),
    ("METAx", "Meta Platforms", "public_equity"),
    ("MSTRx", "MicroStrategy", "public_equity"),
    ("COINx", "Coinbase", "public_equity"),
    ("CRCLx", "Circle", "public_equity"),
    ("HOODx", "Robinhood", "public_equity"),
    ("SPYx", "S&P 500 ETF", "public_equity"),
    ("QQQx", "Nasdaq-100 ETF", "public_equity"),
    ("VCXx", "Fundrise Innovation Fund (SpaceX/OpenAI/Anthropic exposure)", "pre_ipo"),
    ("SPCXx", "SpaceX (synthetic pre-IPO tracker)", "pre_ipo"),
]

NOTES: dict[Category, str] = {
    "public_equity": (
        "Tokenized exposure to an already publicly-listed stock. "
        "Price-only — no shareholder rights."
    ),
    "pre_ipo": (
        "Private/pre-IPO exposure via a synthetic tracker or fund wrapper — not a direct share, "
        "no shareholder rights, structurally different from the public-equity xStocks above."
    ),
}
