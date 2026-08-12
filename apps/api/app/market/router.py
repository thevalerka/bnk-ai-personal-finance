from app.market.budget import BudgetManager
from app.market.cache import Cache
from app.market.providers.base import CallSpec, Provider, ProviderError
from app.market.schemas import Quote


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
    """

    def __init__(
        self,
        providers: dict[str, Provider],
        chains: dict[str, list[str]],
        budget: BudgetManager,
        cache: Cache,
        fresh_ttl_seconds: int = 30,
    ) -> None:
        self._providers = providers
        self._chains = chains
        self._budget = budget
        self._cache = cache
        self._fresh_ttl_seconds = fresh_ttl_seconds

    async def quote(self, capability: str, symbols: list[str]) -> list[Quote]:
        chain = self._chains.get(capability, [])
        stale_fallback: list[Quote] | None = None

        for provider_name in chain:
            provider = self._providers.get(provider_name)
            if provider is None:
                continue

            cache_key = self._cache_key(provider_name, symbols)
            cached = await self._cache.get(cache_key, self._fresh_ttl_seconds)
            if cached is not None:
                if cached.is_fresh:
                    return [Quote.model_validate(item) for item in cached.payload]
                if stale_fallback is None:
                    stale_fallback = [Quote.model_validate(item) for item in cached.payload]

            cost = provider.cost(CallSpec(kind="quote", symbols=tuple(symbols)))
            if not await self._budget.try_consume(provider_name, cost):
                continue

            try:
                quotes = await provider.quote(symbols)
            except ProviderError:
                continue

            await self._cache.set(cache_key, [q.model_dump(mode="json") for q in quotes])
            return quotes

        if stale_fallback is not None:
            return stale_fallback
        raise MarketDataUnavailable(capability, symbols)

    @staticmethod
    def _cache_key(provider_name: str, symbols: list[str]) -> str:
        return f"quote:{provider_name}:{','.join(sorted(symbols))}"
