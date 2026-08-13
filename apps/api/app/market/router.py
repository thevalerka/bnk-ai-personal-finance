from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel

from app.market.budget import BudgetManager
from app.market.cache import Cache
from app.market.providers.base import CallSpec, DateRange, Provider, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

ModelT = TypeVar("ModelT", bound=BaseModel)


class MarketDataUnavailable(Exception):
    """No provider in the capability's chain could serve this request:
    every provider either errored, was over budget, or had no cache to fall
    back on. The API layer turns this into a 503."""

    def __init__(self, capability: str, symbols: list[str]) -> None:
        self.capability = capability
        self.symbols = symbols
        super().__init__(f"no provider available for {capability} {symbols}")


class Router:
    """Picks a provider per capability, with fallback and a budget/cache gate.

    Never calls a vendor that is over its declared budget: it checks cache
    first, then budget, and only then the vendor. On a budget breach or a
    provider error it moves to the next provider in the chain; if the whole
    chain is exhausted it serves the freshest stale cache entry it saw along
    the way, or raises MarketDataUnavailable.

    All four capabilities (quote/candles/news/calendar) share this exact
    policy, so they're implemented as thin wrappers over `_call` — see
    docs/PLAN.md section 3.1 for the cache TTLs each one uses.
    """

    def __init__(
        self,
        providers: dict[str, Provider],
        chains: dict[str, list[str]],
        budget: BudgetManager,
        cache: Cache,
        fresh_ttl_seconds: int = 30,
        news_ttl_seconds: int = 300,
        calendar_ttl_seconds: int = 3600,
    ) -> None:
        self._providers = providers
        self._chains = chains
        self._budget = budget
        self._cache = cache
        self._fresh_ttl_seconds = fresh_ttl_seconds
        self._news_ttl_seconds = news_ttl_seconds
        self._calendar_ttl_seconds = calendar_ttl_seconds

    async def quote(self, capability: str, symbols: list[str]) -> list[Quote]:
        return await self._call(
            capability=capability,
            cache_key=f"quote:{capability}:{','.join(sorted(symbols))}",
            ttl_seconds=self._fresh_ttl_seconds,
            cost=CallSpec(kind="quote", symbols=tuple(symbols)),
            model=Quote,
            invoke=lambda provider: provider.quote(symbols),
        )

    async def candles(self, capability: str, symbol: str, tf: str, limit: int) -> list[Candle]:
        return await self._call(
            capability=capability,
            cache_key=f"candles:{capability}:{symbol}:{tf}:{limit}",
            ttl_seconds=self._fresh_ttl_seconds,
            cost=CallSpec(kind="candles", symbols=(symbol,)),
            model=Candle,
            invoke=lambda provider: provider.candles(symbol, tf, limit),
        )

    async def news(self, capability: str, topics: list[str], since: datetime) -> list[NewsItem]:
        topics_key = ",".join(sorted(topics)) if topics else "*"
        return await self._call(
            capability=capability,
            cache_key=f"news:{capability}:{topics_key}:{since.date().isoformat()}",
            ttl_seconds=self._news_ttl_seconds,
            cost=CallSpec(kind="news", symbols=tuple(topics)),
            model=NewsItem,
            invoke=lambda provider: provider.news(topics, since),
        )

    async def calendar(self, capability: str, window: DateRange) -> list[Event]:
        return await self._call(
            capability=capability,
            cache_key=f"calendar:{capability}:{window.start.isoformat()}:{window.end.isoformat()}",
            ttl_seconds=self._calendar_ttl_seconds,
            cost=CallSpec(kind="calendar"),
            model=Event,
            invoke=lambda provider: provider.calendar(window),
        )

    async def _call(
        self,
        *,
        capability: str,
        cache_key: str,
        ttl_seconds: int,
        cost: CallSpec,
        model: type[ModelT],
        invoke: Callable[[Provider], Awaitable[list[ModelT]]],
    ) -> list[ModelT]:
        chain = self._chains.get(capability, [])
        stale_fallback: list[ModelT] | None = None

        for provider_name in chain:
            provider = self._providers.get(provider_name)
            if provider is None:
                continue

            key = f"{provider_name}:{cache_key}"
            cached = await self._cache.get(key, ttl_seconds)
            if cached is not None:
                if cached.is_fresh:
                    return [model.model_validate(item) for item in cached.payload]
                if stale_fallback is None:
                    stale_fallback = [model.model_validate(item) for item in cached.payload]

            provider_cost = provider.cost(cost)
            if not await self._budget.try_consume(provider_name, provider_cost):
                continue

            try:
                items = await invoke(provider)
            except ProviderError:
                continue

            await self._cache.set(key, [item.model_dump(mode="json") for item in items])
            return items

        if stale_fallback is not None:
            return stale_fallback
        raise MarketDataUnavailable(capability, list(cost.symbols))
