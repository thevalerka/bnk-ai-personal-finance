"""Thin wrapper around Jupiter's (jup.ag) public REST API — token search,
swap quote/build, and Jupiter Lend deposit/withdraw build. Keyless-capable
(lower rate limit) or with a free registered `x-api-key` for the normal
tier (docs/DECISIONS.md ADR-0029). This is the only place in the backend
that knows Jupiter's wire format; everything past `app/jupiter/gateway.py`
sees the canonical schemas in `app/jupiter/schemas.py` instead (CLAUDE.md:
no vendor SDK/shape past the Gateway boundary).

Every call here only ever returns *unsigned* transactions or read-only
data — this client has no notion of a private key and never could sign
anything (CLAUDE.md: backend never holds keys or custody).
"""

import httpx

from app.market.providers.base import ProviderError

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class JupiterClient:
    name = "jupiter"

    def __init__(self, client: httpx.AsyncClient, base_url: str, api_key: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key} if api_key else {}

    async def _get(self, path: str, params: dict[str, str | int | float | bool | None]) -> object:
        try:
            response = await self._client.get(
                f"{self._base_url}{path}", params=params, headers=self._headers
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"jupiter GET {path} failed: {exc}") from exc
        return response.json()

    async def _post(self, path: str, body: dict[str, object]) -> object:
        try:
            response = await self._client.post(
                f"{self._base_url}{path}", json=body, headers=self._headers
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"jupiter POST {path} failed: {exc}") from exc
        return response.json()

    async def search_token(self, query: str) -> dict[str, object] | None:
        """The verified match for a symbol query, or None if nothing
        verified matched. Verified specifically: `/tokens/v2/search` for a
        popular xStock ticker (e.g. "AAPLx") reliably returns copy-cat
        launchpad tokens alongside the real one (same symbol, `isVerified`
        unset, prices off by 8 orders of magnitude — confirmed live against
        the real API before writing this, docs/DECISIONS.md ADR-0029) — an
        unfiltered first-result pick would show a scam token's price under
        a real xStock's name. Never falls back to an unverified result."""
        result = await self._get("/tokens/v2/search", {"query": query})
        if not isinstance(result, list):
            return None
        for token in result:
            if isinstance(token, dict) and token.get("isVerified") is True:
                return token
        return None

    async def lend_tokens(self) -> list[dict[str, object]]:
        result = await self._get("/lend/v1/earn/tokens", {})
        return result if isinstance(result, list) else []

    async def swap_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: str,
        slippage_bps: int,
        platform_fee_bps: int,
    ) -> dict[str, object]:
        params: dict[str, str | int | float | bool | None] = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount,
            "slippageBps": slippage_bps,
        }
        if platform_fee_bps > 0:
            params["platformFeeBps"] = platform_fee_bps
        result = await self._get("/swap/v1/quote", params)
        if not isinstance(result, dict):
            raise ProviderError("jupiter swap quote returned an unexpected shape")
        return result

    async def build_swap_transaction(
        self, wallet_address: str, quote: dict[str, object], fee_account: str
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "userPublicKey": wallet_address,
            "quoteResponse": quote,
            "wrapAndUnwrapSol": True,
            "dynamicSlippage": True,
        }
        if fee_account:
            body["feeAccount"] = fee_account
        result = await self._post("/swap/v1/swap", body)
        if not isinstance(result, dict):
            raise ProviderError("jupiter build-swap-transaction returned an unexpected shape")
        return result

    async def build_lend_transaction(
        self, action: str, asset_mint: str, wallet_address: str, amount: str
    ) -> dict[str, object]:
        path = "/lend/v1/earn/deposit" if action == "deposit" else "/lend/v1/earn/withdraw"
        result = await self._post(
            path, {"asset": asset_mint, "signer": wallet_address, "amount": amount}
        )
        if not isinstance(result, dict):
            raise ProviderError("jupiter build-lend-transaction returned an unexpected shape")
        return result
