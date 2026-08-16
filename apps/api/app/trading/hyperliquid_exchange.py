"""Post-hoc verification against Hyperliquid's public testnet info API.

Order signing and submission happen entirely client-side (browser wallet via
`@nktkas/hyperliquid`, docs/DECISIONS.md ADR-0028): the backend never
builds, signs, or relays a trading action — `CLAUDE.md`'s "backend never
holds keys or custody" applies just as much to msgpack/EIP-712 action
construction as it does to the key itself, so there is nothing for this
module to sign. Its only job is to confirm a claimed fill actually happened
on Hyperliquid before `/trading/fills` logs it for commission accounting,
so that endpoint can't be fed fabricated trades.
"""

import httpx

from app.market.providers.base import ProviderError

TESTNET_INFO_URL = "https://api.hyperliquid-testnet.xyz/info"


class HyperliquidExchangeClient:
    name = "hyperliquid_exchange"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def order_exists(self, wallet_address: str, order_id: int) -> bool:
        """True if Hyperliquid's testnet knows about this (wallet, oid) pair
        at all — filled, open, canceled, whatever. `{"status": "unknownOid"}`
        is the documented not-found sentinel; anything else means the order
        is real, which is all `/trading/fills` needs to know."""
        try:
            response = await self._client.post(
                TESTNET_INFO_URL,
                json={"type": "orderStatus", "user": wallet_address, "oid": order_id},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"hyperliquid orderStatus check failed: {exc}") from exc
        body = response.json()
        return isinstance(body, dict) and body.get("status") != "unknownOid"
