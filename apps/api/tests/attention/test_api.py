from collections.abc import Generator

import anyio
import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.attention.identity import COOKIE_NAME
from app.config import get_settings
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    # https:// base_url, not the TestClient default http://testserver: the
    # profile cookie is Secure whenever Settings.env != "development" (true
    # for this dev box's own apps/api/.ratx, which points at the deployed
    # env), and a Secure cookie is correctly dropped by any HTTP transport —
    # same as a real browser would. Testing over https keeps that behavior
    # real rather than only exercising the insecure-cookie code path.
    with TestClient(app, base_url="https://testserver") as c:
        yield c
    # HTTP-level tests hit the app's own real pool (not the transactional
    # db_conn fixture other attention tests use), so clean up whatever
    # profile the cookie jar picked up along the way.
    raw = c.cookies.get(COOKIE_NAME)
    if raw:
        profile_id = raw.split(".", 1)[0]

        async def _delete() -> None:
            conn = await asyncpg.connect(dsn=get_settings().database_url)
            try:
                await conn.execute("DELETE FROM profiles WHERE id = $1", profile_id)
            finally:
                await conn.close()

        anyio.run(_delete)


def test_first_visit_sets_a_profile_cookie(client: TestClient) -> None:
    response = client.get("/profile/vector")
    assert response.status_code == 200
    assert response.json() == {}
    assert COOKIE_NAME in response.cookies


def test_layout_with_no_events_splits_evenly(client: TestClient) -> None:
    response = client.get("/profile/layout")
    assert response.status_code == 200
    blocks = response.json()["blocks"]
    assert {b["block_type"] for b in blocks} == {"quotes", "yield_curve", "heatmap"}
    assert sum(b["columns"] for b in blocks) == 12


def test_posting_events_reshapes_the_layout(client: TestClient) -> None:
    client.get("/profile/vector")  # establish the cookie first
    events = {
        "events": [
            {"node_id": "fixed_income.rates_ust.long_end", "kind": "click"} for _ in range(5)
        ]
    }
    post_response = client.post("/profile/events", json=events)
    assert post_response.status_code == 204

    layout = client.get("/profile/layout").json()
    by_type = {b["block_type"]: b for b in layout["blocks"]}
    assert by_type["yield_curve"]["priority"] == 1
    assert by_type["yield_curve"]["columns"] > by_type["quotes"]["columns"]


def test_posting_unknown_node_returns_422(client: TestClient) -> None:
    response = client.post(
        "/profile/events", json={"events": [{"node_id": "nonsense", "kind": "click"}]}
    )
    assert response.status_code == 422


def test_explain_unknown_taxonomy_id_returns_404(client: TestClient) -> None:
    response = client.get("/profile/explain", params={"node_id": "nonsense"})
    assert response.status_code == 404


def test_explain_reconciles_with_vector_over_http(client: TestClient) -> None:
    node_id = "crypto.majors.btc"
    client.post("/profile/events", json={"events": [{"node_id": node_id, "kind": "click"}]})

    vector = client.get("/profile/vector").json()
    explanation = client.get("/profile/explain", params={"node_id": node_id}).json()
    assert vector[node_id] == pytest.approx(explanation["score"])
    assert len(explanation["source_events"]) == 1


def test_get_personas_lists_all_four(client: TestClient) -> None:
    response = client.get("/profile/personas")
    assert response.status_code == 200
    names = {p["name"] for p in response.json()}
    assert names == {"macro", "equity_pm", "options_trader", "crypto_native"}


def test_view_as_macro_replaces_the_cookie_and_reshapes_layout(client: TestClient) -> None:
    client.get("/profile/vector")
    original_cookie = client.cookies[COOKIE_NAME]

    response = client.post("/profile/persona/macro")
    assert response.status_code == 200
    body = response.json()
    assert body["persona"] == "macro"
    by_type = {b["block_type"]: b for b in body["layout"]["blocks"]}
    assert by_type["yield_curve"]["priority"] == 1

    assert client.cookies[COOKIE_NAME] != original_cookie
    me = client.get("/profile/me").json()
    assert me["persona"] == "macro"
    assert me["profile_id"] == body["profile_id"]


def test_view_as_unknown_persona_returns_404(client: TestClient) -> None:
    response = client.post("/profile/persona/day_trader")
    assert response.status_code == 404


def test_reset_clears_persona_and_starts_an_empty_profile(client: TestClient) -> None:
    client.post("/profile/persona/crypto_native")
    response = client.post("/profile/reset")
    assert response.status_code == 200
    body = response.json()
    assert body["persona"] is None
    columns = [b["columns"] for b in body["layout"]["blocks"]]
    assert set(columns) == {4}  # no events yet -> even 4/4/4 split

    me = client.get("/profile/me").json()
    assert me["profile_id"] == body["profile_id"]
    assert me["persona"] is None
