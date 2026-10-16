"""Initial schema: tenants, trucks, stations, prices, IFTA, routes.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-12
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostGIS is not optional: the corridor query and the per-state split are
    # spatial operations, not conveniences.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "truck_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("mpg", sa.Float(), nullable=False),
        sa.Column("tank_gallons", sa.Float(), nullable=False),
        sa.Column("reserve_fraction", sa.Float(), nullable=False),
        sa.Column("height_m", sa.Float(), nullable=False),
        sa.Column("width_m", sa.Float(), nullable=False),
        sa.Column("length_m", sa.Float(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("axles", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_truck_profiles_tenant_id", "truck_profiles", ["tenant_id"])

    op.create_table(
        "fuel_stations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT", srid=4326, spatial_index=False, from_text="ST_GeomFromEWKT"
            ),
            nullable=False,
        ),
        sa.Column("accepts_card", sa.Boolean(), nullable=False),
        sa.Column("has_truck_lanes", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_fuel_stations_provider_external"),
    )
    op.create_index("ix_fuel_stations_tenant_id", "fuel_stations", ["tenant_id"])
    op.create_index("ix_fuel_stations_state", "fuel_stations", ["state"])
    op.create_index("ix_fuel_stations_geom", "fuel_stations", ["geom"], postgresql_using="gist")

    op.create_table(
        "fuel_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fuel_type", sa.String(length=20), nullable=False),
        sa.Column("price_per_gallon", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("is_contract_price", sa.Boolean(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["station_id"], ["fuel_stations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "station_id", "fuel_type", "effective_date", name="uq_fuel_prices_station_type_date"
        ),
    )
    op.create_index("ix_fuel_prices_station_id", "fuel_prices", ["station_id"])
    op.create_index("ix_fuel_prices_effective_date", "fuel_prices", ["effective_date"])

    op.create_table(
        "ifta_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("fuel_type", sa.String(length=20), nullable=False),
        sa.Column("tax_per_gallon", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "state_code", "fuel_type", "effective_from", name="uq_ifta_rates_state_type_from"
        ),
    )
    op.create_index("ix_ifta_rates_state_code", "ifta_rates", ["state_code"])

    op.create_table(
        "us_states",
        sa.Column("code", sa.String(length=2), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index("ix_us_states_geom", "us_states", ["geom"], postgresql_using="gist")

    op.create_table(
        "scraper_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("storage_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider"),
    )

    op.create_table(
        "routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("truck_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin_label", sa.String(length=300), nullable=False),
        sa.Column("origin_lat", sa.Float(), nullable=False),
        sa.Column("origin_lon", sa.Float(), nullable=False),
        sa.Column("destination_label", sa.String(length=300), nullable=False),
        sa.Column("destination_lat", sa.Float(), nullable=False),
        sa.Column("destination_lon", sa.Float(), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(
                geometry_type="LINESTRING",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
            ),
            nullable=False,
        ),
        sa.Column("total_miles", sa.Float(), nullable=False),
        sa.Column("total_minutes", sa.Float(), nullable=False),
        sa.Column("ifta_mode", sa.String(length=8), nullable=False),
        sa.Column("corridor_miles", sa.Float(), nullable=False),
        sa.Column("start_fuel_gallons", sa.Float(), nullable=False),
        sa.Column("total_fuel_cost", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total_gallons", sa.Float(), nullable=False),
        sa.Column("baseline_cost", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("savings_usd", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("feasible", sa.Boolean(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["truck_profile_id"], ["truck_profiles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_routes_tenant_id", "routes", ["tenant_id"])
    op.create_index("ix_routes_geometry", "routes", ["geometry"], postgresql_using="gist")

    op.create_table(
        "route_fuel_stops",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("route_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("stop_type", sa.String(length=16), nullable=False),
        sa.Column("mile_marker", sa.Float(), nullable=False),
        sa.Column("detour_miles", sa.Float(), nullable=False),
        sa.Column("gallons", sa.Float(), nullable=False),
        sa.Column("price_per_gallon", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("net_price_per_gallon", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("cost", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("arrival_gallons", sa.Float(), nullable=False),
        sa.Column("departure_gallons", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["station_id"], ["fuel_stations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_route_fuel_stops_route_id", "route_fuel_stops", ["route_id"])

    op.create_table(
        "route_state_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("route_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("miles", sa.Float(), nullable=False),
        sa.Column("gallons", sa.Float(), nullable=False),
        sa.Column("tax_per_gallon", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("tax_owed", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_route_state_segments_route_id", "route_state_segments", ["route_id"])


def downgrade() -> None:
    op.drop_table("route_state_segments")
    op.drop_table("route_fuel_stops")
    op.drop_table("routes")
    op.drop_table("scraper_sessions")
    op.drop_index("ix_us_states_geom", table_name="us_states")
    op.drop_table("us_states")
    op.drop_table("ifta_rates")
    op.drop_table("fuel_prices")
    op.drop_index("ix_fuel_stations_geom", table_name="fuel_stations")
    op.drop_table("fuel_stations")
    op.drop_table("truck_profiles")
    op.drop_table("tenants")
