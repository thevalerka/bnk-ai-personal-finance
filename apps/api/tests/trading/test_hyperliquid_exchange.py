import httpx
import respx

from app.trading.hyperliquid_exchange import TESTNET_INFO_URL, HyperliquidExchangeClient


@respx.mock
async def test_order_exists_true_for_a_known_order(http_client: httpx.AsyncClient) -> None:
    respx.post(TESTNET_INFO_URL).mock(
        return_value=httpx.Response(200, json={"status": "order", "order": {"status": "filled"}})
    )
    client = HyperliquidExchangeClient(http_client)

    assert await client.order_exists("0xabc", 12345) is True


@respx.mock
async def test_order_exists_false_for_unknown_oid(http_client: httpx.AsyncClient) -> None:
    respx.post(TESTNET_INFO_URL).mock(
        return_value=httpx.Response(200, json={"status": "unknownOid"})
    )
    client = HyperliquidExchangeClient(http_client)

    assert await client.order_exists("0xabc", 99999) is False
