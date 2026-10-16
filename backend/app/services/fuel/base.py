"""Fuel-price provider interface.

Prices reach the optimizer through exactly one table (``fuel_prices``) and exactly
one interface, so the source can change without touching anything downstream. That
matters here more than usual: the customer's fuel-card portal is behind 2FA and
nobody has handed over credentials yet, so the MVP must run on a substitute source
today and switch to contract prices later without a rewrite.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class StationRecord:
    """Station facts, keyed by the source's own id."""

    external_id: str
    name: str
    state: str
    lat: float
    lon: float
    brand: str | None = None
    address: str | None = None
    city: str | None = None
    accepts_card: bool = True
    has_truck_lanes: bool = True


@dataclass(frozen=True)
class PriceRecord:
    """One price for one station on one day.

    ``is_contract_price`` is the honesty flag: True only when the number came from
    the company's own fuel-card account. A retail or modelled price must never be
    presented as the contract price, because the whole savings claim rests on it.
    """

    external_id: str
    price_per_gallon: float
    effective_date: date
    fuel_type: str = "diesel"
    is_contract_price: bool = False


@dataclass
class FetchReport:
    """What a refresh run did, for the Celery task to log and store."""

    provider: str
    stations: int = 0
    prices: int = 0
    status: str = "ok"  # ok | needs_login | error
    message: str | None = None
    warnings: list[str] = field(default_factory=list)


class FuelPriceUnavailable(RuntimeError):
    """The source could not be read (network, layout change, expired session)."""


class NeedsLogin(FuelPriceUnavailable):
    """A human has to log in once before this source can be read.

    Raised instead of a generic failure so the refresh task can flag the session
    as ``needs_login`` rather than retrying forever against a login wall.
    """


class FuelPriceProvider(ABC):
    name: str = "base"

    #: True when this provider reports the company's negotiated prices rather
    #: than retail or modelled ones.
    contract_prices: bool = False

    @abstractmethod
    async def fetch_stations(self) -> list[StationRecord]:
        """Stations where the company's card is accepted."""

    @abstractmethod
    async def fetch_prices(self, stations: list[StationRecord]) -> list[PriceRecord]:
        """Today's price for each station."""
