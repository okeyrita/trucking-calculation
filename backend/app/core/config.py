"""Application settings, loaded from the environment (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

FuelProviderName = Literal["seed", "public_eia", "contract_portal"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://trucking:trucking@localhost:5432/trucking"
    db_echo: bool = False

    # Routing
    graphhopper_api_key: str = ""
    graphhopper_base_url: str = "https://graphhopper.com/api/1"
    routing_truck_profile_enabled: bool = True
    routing_timeout_seconds: float = 30.0

    # Fuel prices
    fuel_price_provider: FuelProviderName = "seed"
    scraper_state_dir: str = "/var/lib/trucking/scraper"
    contract_portal_url: str = ""
    contract_portal_username: str = ""
    contract_portal_password: str = ""
    # Fragment of the portal's station-map API URL, e.g. "/api/locations/search".
    # Filled in once someone can watch the portal's network traffic.
    contract_portal_map_api_pattern: str = ""

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    fuel_price_refresh_cron_hour: int = 7

    # Fuel-plan defaults. Overridable per request / per truck profile.
    default_corridor_miles: float = 3.0
    default_mpg: float = 6.5
    default_tank_gallons: float = 200.0
    default_reserve_fraction: float = 0.15
    # What a fuel stop costs beyond the fuel (driver time, detour, manoeuvring).
    # Stops that save less than this are consolidated away.
    default_stop_overhead_usd: float = 8.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
