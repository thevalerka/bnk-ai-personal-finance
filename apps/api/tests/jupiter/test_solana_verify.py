import httpx
import respx

from app.jupiter.solana_verify import SolanaVerifier

RPC_URL = "https://api.mainnet-beta.solana.com"


@respx.mock
async def test_transaction_succeeded_true_for_a_confirmed_signature(
    http_client: httpx.AsyncClient,
) -> None:
    respx.post(RPC_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "result": {
                    "context": {"slot": 1},
                    "value": [{"confirmationStatus": "finalized", "err": None}],
                },
                "id": 1,
            },
        )
    )
    verifier = SolanaVerifier(http_client, RPC_URL)

    assert await verifier.transaction_succeeded("sig123") is True


@respx.mock
async def test_transaction_succeeded_false_for_an_onchain_error(
    http_client: httpx.AsyncClient,
) -> None:
    respx.post(RPC_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "result": {
                    "context": {"slot": 1},
                    "value": [{"confirmationStatus": "finalized", "err": {"InstructionError": []}}],
                },
                "id": 1,
            },
        )
    )
    verifier = SolanaVerifier(http_client, RPC_URL)

    assert await verifier.transaction_succeeded("sig123") is False


@respx.mock
async def test_transaction_succeeded_false_for_an_unknown_signature(
    http_client: httpx.AsyncClient,
) -> None:
    respx.post(RPC_URL).mock(
        return_value=httpx.Response(
            200,
            json={"jsonrpc": "2.0", "result": {"context": {"slot": 1}, "value": [None]}, "id": 1},
        )
    )
    verifier = SolanaVerifier(http_client, RPC_URL)

    assert await verifier.transaction_succeeded("sig-does-not-exist") is False
