#!/usr/bin/env python3
"""Probe every source in config/sources.yaml and report what is actually alive.

Run this BEFORE writing any adapter, and in CI weekly. Free tiers and RSS URLs rot;
this script is how you find out on your terms instead of in production.

    python scripts/check_sources.py                  # probe everything
    python scripts/check_sources.py --tier 0         # primary sources only
    python scripts/check_sources.py --source fred    # one source
    python scripts/check_sources.py --json           # machine-readable, for CI

Exit codes: 0 = all tier-0 sources healthy, 1 = a tier-0 source is down.
Non-primary failures warn but do not fail the build: the Router has fallbacks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sources.yaml"

# Probe URLs per source. A probe should be the cheapest possible real call:
# it proves auth works, the host resolves, and the response shape is sane.
# {KEY} placeholders are filled from the environment.
PROBES: dict[str, dict[str, Any]] = {
    "fred": {
        "url": "https://api.stlouisfed.org/fred/series/observations",
        "params": {"series_id": "DGS10", "file_type": "json", "limit": 1, "sort_order": "desc"},
        "auth_env": "FRED_API_KEY",
        "auth_param": "api_key",
        "expect_json_path": ["observations"],
    },
    "federal_reserve": {
        "url": "https://www.federalreserve.gov/feeds/press_monetary.xml",
        "expect_contains": "<rss",
    },
    "treasury_fiscaldata": {
        "url": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
               "/v2/accounting/od/avg_interest_rates",
        "params": {"page[size]": 1},
        "expect_json_path": ["data"],
    },
    "sec_edgar": {
        "url": "https://data.sec.gov/submissions/CIK0000320193.json",  # Apple
        "expect_json_path": ["cik"],
        "needs_user_agent": True,
    },
    "bls": {"url": "https://www.bls.gov/schedule/news_release/", "expect_contains": "html"},
    "bea": {"url": "https://apps.bea.gov/api/data", "params": {"method": "GETDATASETLIST"},
            "auth_env": "BEA_API_KEY", "auth_param": "UserID", "optional": True},
    "ecb": {"url": "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.MRR_FR.LEV",
            "params": {"lastNObservations": 1, "format": "jsondata"}},
    "white_house": {"url": "https://www.whitehouse.gov/briefing-room/feed/", "optional": True},
    "congress": {"url": "https://api.congress.gov/v3/committee-meeting",
                 "auth_env": "CONGRESS_API_KEY", "auth_param": "api_key", "optional": True},
    "finnhub": {
        "url": "https://finnhub.io/api/v1/quote",
        "params": {"symbol": "AAPL"},
        "auth_env": "FINNHUB_API_KEY",
        "auth_header": "X-Finnhub-Token",
        "expect_json_path": ["c"],
    },
    "alpaca": {
        "url": "https://data.alpaca.markets/v2/stocks/quotes/latest",
        "params": {"symbols": "AAPL", "feed": "iex"},
        "auth_headers": {"APCA-API-KEY-ID": "ALPACA_KEY_ID",
                         "APCA-API-SECRET-KEY": "ALPACA_SECRET"},
        "expect_json_path": ["quotes"],
    },
    "alpha_vantage": {
        "url": "https://www.alphavantage.co/query",
        "params": {"function": "NEWS_SENTIMENT", "tickers": "AAPL", "limit": 1},
        "auth_env": "ALPHAVANTAGE_API_KEY", "auth_param": "apikey",
        "optional": True,
        "note": "Free tier is ~25 req/day — a probe costs 4% of your daily budget.",
    },
    "marketaux": {
        "url": "https://api.marketaux.com/v1/news/all",
        "params": {"symbols": "AAPL", "limit": 1},
        "auth_env": "MARKETAUX_API_KEY", "auth_param": "api_token", "optional": True,
    },
    "fmp": {
        "url": "https://financialmodelingprep.com/stable/economic-calendar",
        "auth_env": "FMP_API_KEY", "auth_param": "apikey", "optional": True,
    },
    "gdelt": {
        "url": "https://api.gdeltproject.org/api/v2/doc/doc",
        "params": {"query": "federal reserve", "mode": "artlist", "format": "json", "maxrecords": 1},
        "optional": True,
    },
    "polymarket": {"url": "https://gamma-api.polymarket.com/markets", "params": {"limit": 1}},
    "kalshi": {"url": "https://api.elections.kalshi.com/trade-api/v2/markets",
               "params": {"limit": 1}, "optional": True},
    "binance_public": {"url": "https://api.binance.com/api/v3/ticker/price",
                       "params": {"symbol": "BTCUSDT"}, "expect_json_path": ["price"]},
    "hyperliquid": {"url": "https://api.hyperliquid.xyz/info", "method": "POST",
                    "json": {"type": "meta"}},
    "pyth": {"url": "https://hermes.pyth.network/v2/price_feeds", "params": {"query": "BTC"},
             "optional": True},
}


@dataclass
class Result:
    source: str
    tier: int
    declared_status: str
    ok: bool
    http_status: int | None
    latency_ms: int | None
    detail: str

    @property
    def blocking(self) -> bool:
        return self.tier == 0 and not self.ok


def _dig(obj: Any, path: list[str]) -> bool:
    for key in path:
        if isinstance(obj, dict) and key in obj:
            obj = obj[key]
        elif isinstance(obj, list) and obj:
            obj = obj[0]
        else:
            return False
    return True


async def probe(client: httpx.AsyncClient, name: str, cfg: dict, ua: str) -> Result:
    spec = PROBES.get(name)
    tier = cfg.get("tier", 9)
    declared = cfg.get("status", "unknown")

    if spec is None:
        return Result(name, tier, declared, True, None, None, "no probe defined — skipped")

    params = dict(spec.get("params", {}))
    headers = {"User-Agent": ua} if spec.get("needs_user_agent", True) else {}

    # Resolve auth from the environment; a missing optional key is a skip, not a failure.
    if env := spec.get("auth_env"):
        value = os.getenv(env)
        if not value:
            msg = f"{env} not set"
            return Result(name, tier, declared, spec.get("optional", False) or tier > 0,
                          None, None, msg + " — skipped")
        if p := spec.get("auth_param"):
            params[p] = value
        if h := spec.get("auth_header"):
            headers[h] = value
    for header, env_name in spec.get("auth_headers", {}).items():
        value = os.getenv(env_name)
        if not value:
            return Result(name, tier, declared, True, None, None, f"{env_name} not set — skipped")
        headers[header] = value

    started = time.perf_counter()
    try:
        method = spec.get("method", "GET")
        resp = await client.request(
            method, spec["url"], params=params or None,
            json=spec.get("json"), headers=headers, timeout=15.0,
        )
        elapsed = int((time.perf_counter() - started) * 1000)
    except Exception as exc:  # noqa: BLE001 — a probe failure is data, not an error
        return Result(name, tier, declared, False, None, None, f"{type(exc).__name__}: {exc}")

    if resp.status_code >= 400:
        return Result(name, tier, declared, False, resp.status_code, elapsed,
                      f"HTTP {resp.status_code}: {resp.text[:160]}")

    if needle := spec.get("expect_contains"):
        if needle.lower() not in resp.text[:4000].lower():
            return Result(name, tier, declared, False, resp.status_code, elapsed,
                          f"body missing expected marker {needle!r}")

    if path := spec.get("expect_json_path"):
        try:
            if not _dig(resp.json(), path):
                return Result(name, tier, declared, False, resp.status_code, elapsed,
                              f"response shape changed — {'.'.join(path)} not found")
        except ValueError:
            return Result(name, tier, declared, False, resp.status_code, elapsed,
                          "expected JSON, got something else")

    return Result(name, tier, declared, True, resp.status_code, elapsed, "ok")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", type=int, help="probe only this tier")
    ap.add_argument("--source", help="probe a single source by id")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    config = yaml.safe_load(CONFIG.read_text())
    ua = config["defaults"]["user_agent"]
    sources = config["sources"]

    selected = {
        name: cfg for name, cfg in sources.items()
        if (args.source is None or name == args.source)
        and (args.tier is None or cfg.get("tier") == args.tier)
        and cfg.get("kind") != "scraper"
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(*(probe(client, n, c, ua) for n, c in selected.items()))

    results.sort(key=lambda r: (r.tier, not r.blocking, r.source))

    if args.as_json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        width = max(len(r.source) for r in results) + 2
        current_tier = None
        for r in results:
            if r.tier != current_tier:
                current_tier = r.tier
                print(f"\n── tier {current_tier} " + "─" * 50)
            mark = "PASS" if r.ok else "FAIL"
            latency = f"{r.latency_ms:>5}ms" if r.latency_ms else "     —"
            print(f"  [{mark}] {r.source:<{width}} {latency}  {r.detail}")

        broken = [r for r in results if r.blocking]
        degraded = [r for r in results if not r.ok and not r.blocking]
        print()
        if broken:
            print(f"{len(broken)} PRIMARY source(s) down: {', '.join(r.source for r in broken)}")
            print("The calendar depends on these. Fix before building adapters.")
        if degraded:
            print(f"{len(degraded)} non-primary degraded (Router will fall back): "
                  f"{', '.join(r.source for r in degraded)}")
        if not broken and not degraded:
            print("All probed sources healthy.")
        print("\nIf a source is permanently dead, set `status: dead` in config/sources.yaml,")
        print("remove it from every routing chain, and note it in docs/DECISIONS.md.")

    return 1 if any(r.blocking for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
