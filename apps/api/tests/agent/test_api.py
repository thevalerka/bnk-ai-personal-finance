from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

import app.api.agent as agent_module
import app.api.profile as profile_module
from app.agent.budget import AgentBudget
from app.config import Settings, get_settings
from app.main import app
from tests.agent.conftest import (
    FakeAsyncAnthropic,
    FakeContentBlockDeltaEvent,
    FakeMessage,
    FakeTextBlock,
    FakeTextDelta,
    build_gateway,
)
from tests.market.conftest import FakeProvider


@pytest.fixture(autouse=True)
def _restore_settings_cache() -> Iterator[None]:
    yield
    get_settings.cache_clear()


def _configured_settings() -> Settings:
    # env="development" explicitly: apps/api/.ratx on this checkout is the
    # real production file (ENV=production) — pydantic-settings reads it in
    # test runs too, which would otherwise make resolve_profile's cookie
    # Secure-flagged and TestClient's plain-http transport would silently
    # never resend it on a second request.
    return Settings(
        anthropic_api_key="sk-ant-test-key", agent_model="claude-sonnet-5", env="development"
    )


@pytest.fixture
def configured_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patched on both modules — each has its own `from app.config import
    # get_settings` binding, so patching one doesn't reach the other.
    monkeypatch.setattr(agent_module, "get_settings", _configured_settings)
    monkeypatch.setattr(profile_module, "get_settings", _configured_settings)


def test_stream_503s_when_no_api_key_is_configured() -> None:
    # The real, current state of this deployment (docs/STATE.md — key not
    # added yet) — no mocking needed, this is what get_settings() actually
    # returns from an unconfigured .ratx.
    with TestClient(app) as client:
        response = client.post("/agent/stream", json={"message": "hi"})
    assert response.status_code == 503


def test_stream_422s_on_empty_message(configured_settings: None) -> None:
    with TestClient(app) as client:
        response = client.post("/agent/stream", json={"message": "   "})
    assert response.status_code == 422


def test_stream_422s_on_message_too_long(configured_settings: None) -> None:
    with TestClient(app) as client:
        response = client.post("/agent/stream", json={"message": "x" * 2001})
    assert response.status_code == 422


def test_stream_happy_path_returns_sse_text_and_done(configured_settings: None) -> None:
    fake_client = FakeAsyncAnthropic(
        turns=[
            (
                [FakeContentBlockDeltaEvent(delta=FakeTextDelta(text="hello there"))],
                FakeMessage(content=[FakeTextBlock(text="hello there")], stop_reason="end_turn"),
            )
        ]
    )
    with TestClient(app) as client:
        redis: Redis = app.state.market_gateway.redis
        app.state.market_gateway = build_gateway(redis, {"finnhub": FakeProvider("finnhub")})
        app.state.agent_budget = AgentBudget(
            redis, monthly_token_budget=1_000_000, rate_limit_per_minute=10
        )
        app.state.anthropic_client = fake_client

        response = client.post("/agent/stream", json={"message": "hi there"})

    assert response.status_code == 200
    assert "event: text" in response.text
    assert '"text": "hello there"' in response.text
    assert "event: done" in response.text
    # A first-visit request also mints the anonymous profile cookie, same
    # as every /profile/* endpoint (app/api/profile.py's resolve_profile).
    assert "amt_profile" in response.headers.get("set-cookie", "")


def test_stream_rate_limits_a_profile_after_the_configured_count(configured_settings: None) -> None:
    def one_turn() -> FakeAsyncAnthropic:
        return FakeAsyncAnthropic(
            turns=[
                ([], FakeMessage(content=[FakeTextBlock(text="ok")], stop_reason="end_turn")),
            ]
        )

    with TestClient(app) as client:
        redis: Redis = app.state.market_gateway.redis
        app.state.market_gateway = build_gateway(redis, {})
        app.state.agent_budget = AgentBudget(
            redis, monthly_token_budget=1_000_000, rate_limit_per_minute=1
        )

        # TestClient keeps a cookie jar across requests on the same
        # instance, same as a real browser — the profile cookie the first
        # response sets is what scopes the second request's rate limit.
        app.state.anthropic_client = one_turn()
        client.post("/agent/stream", json={"message": "one"})

        app.state.anthropic_client = one_turn()
        second = client.post("/agent/stream", json={"message": "two"})

    assert "Rate limit exceeded" in second.text
