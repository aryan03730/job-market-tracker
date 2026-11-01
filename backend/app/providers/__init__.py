"""Provider registry. To add a source: write a Provider subclass and list it here."""
from .adzuna import AdzunaProvider
from .arbeitnow import ArbeitnowProvider
from .base import BudgetExhausted, Provider, ProviderError, RawJob
from .himalayas import HimalayasProvider
from .jobicy import JobicyProvider
from .remoteok import RemoteOKProvider
from .remotive import RemotiveProvider
from .themuse import TheMuseProvider
from .usajobs import USAJobsProvider

REGISTRY: dict[str, type[Provider]] = {
    p.name: p
    for p in (
        AdzunaProvider, USAJobsProvider, RemotiveProvider, JobicyProvider,
        TheMuseProvider, RemoteOKProvider, HimalayasProvider, ArbeitnowProvider,
    )
}

__all__ = ["REGISTRY", "Provider", "ProviderError", "BudgetExhausted", "RawJob"]
