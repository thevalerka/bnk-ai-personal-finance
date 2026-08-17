"""Post-hoc verification against a public Solana RPC — same role as
`app/trading/hyperliquid_exchange.py` plays for Hyperliquid fills. Signing
and submission happen entirely client-side (the browser wallet signs the
unsigned transaction this backend built and sends it straight to Solana);
this module's only job is to confirm a claimed signature really landed
on-chain, successfully, before `/jupiter/*-fills` logs it — so those
endpoints can't be fed a fabricated or failed transaction.
"""

import httpx

from app.market.providers.base import ProviderError


class SolanaVerifier:
    name = "solana_verify"

    def __init__(self, client: httpx.AsyncClient, rpc_url: str) -> None:
        self._client = client
        self._rpc_url = rpc_url

    async def transaction_succeeded(self, signature: str) -> bool:
        try:
            response = await self._client.post(
                self._rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignatureStatuses",
                    "params": [[signature], {"searchTransactionHistory": True}],
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"solana getSignatureStatuses failed: {exc}") from exc
        body = response.json()
        if not isinstance(body, dict):
            return False
        result = body.get("result")
        values = result.get("value") if isinstance(result, dict) else None
        if not isinstance(values, list) or not values or not isinstance(values[0], dict):
            return False
        status = values[0]
        # err is None on success; a populated err object means the
        # transaction landed but failed on-chain — never trusted as a fill.
        confirmed = status.get("confirmationStatus") in ("confirmed", "finalized")
        return confirmed and status.get("err") is None
