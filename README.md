# trucking-calculation


Данный проект - это сырое  МВП решение по бизнес приложению для грузоперевозок по США, которое было проверено и протестировано на минимальных бесплатных данных. 

МВП решение было сделано для заказчика, но диалог прервался. Решение выполнено с использованием Claude Code Opus. 

# Routing & Fuel Control (MVP)

Truck-friendly routing with fuel-cost optimization for US long-haul Class 8 operations.

Give the system an origin and a destination; it returns a truck-legal route plus the
cheapest way to fuel it — which card-accepting stations to use, how many gallons to buy
at each, and how much that beats fuelling without guidance.

This is the first module of the platform described in
[TZ.md](TZ.md).

## What it does

- **Truck-legal routing** via GraphHopper Cloud, with the truck's height, width, length,
  weight and axle count passed through.
- **Fuel optimization** over the stations along the route: a provably optimal algorithm
  for the "gas station problem" — buy just enough to reach a cheaper station, or fill up
  when nothing cheaper is in range.
- **Virtual tank** per truck profile: tank size, MPG and a safety reserve the plan never
  dips into. Fuel economy is MPG throughout (`gallons = miles / mpg`), the US convention.
- **IFTA switch**: optimize on the price on the stele (`pump`) or on the price after the
  state's fuel-tax credit (`net`). It is not a display toggle — the basis changes which
  stations win, because a high-tax state with a low pump price can be the cheaper buy.
- **Stops a driver would actually make**: the mathematical optimum likes to buy a tenth
  of a gallon at one pump to reach a marginally cheaper one at the same interchange. Such
  stops are removed (see [Practical stops](#practical-stops)).
- **Savings figure**: every plan is priced against a baseline driver who ignores price
  (see [How the savings figure is computed](#how-the-savings-figure-is-computed)).
- **Per-state mileage and gallons**, the raw material of an IFTA return.
- **History**: every plan is stored with its geometry, stops and savings.
- **Reroute**: replan from the truck's current position and current tank level, for closed
  roads, weather or delays.
- **SPA** with a map, the stop table, the savings card and per-state breakdown, in
  English, Spanish and Russian.

## Quick start

```bash
cp .env.example .env
# Put a GraphHopper key in .env — get one at https://graphhopper.com/dashboard/
docker compose up --build
```

Then:

- API and Swagger UI — http://localhost:8000/docs
- SPA — http://localhost:5173
- Health and effective configuration — http://localhost:8000/api/v1/health

The API container runs migrations and seeds reference data on start, so the first request
works without further setup.

### Example request

```bash
curl -s -X POST http://localhost:8000/api/v1/routes/plan \
  -H 'Content-Type: application/json' \
  -d '{
        "origin": {"query": "Dallas, TX"},
        "destination": {"query": "Chicago, IL"},
        "start_fuel_gallons": 40,
        "ifta_mode": "pump",
        "corridor_miles": 5
      }' | jq '{miles: .total_miles, cost: .total_fuel_cost, saved: .savings.savings_usd, stops: [.stops[] | {name, mile_marker, gallons, price_per_gallon}]}'
```

## Running without Docker

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
# Point DATABASE_URL at a PostGIS database, then:
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli seed
.venv/bin/uvicorn app.main:app --reload

cd ../frontend && npm install && npm run dev
```

## Tests

```bash
cd backend && .venv/bin/python -m pytest        # 55 offline + 15 database tests
cd frontend && npm run typecheck
```

The offline suite needs no database, no network and no API key. The database tests skip
themselves unless `DATABASE_URL` points at a reachable PostGIS instance; they use a
dedicated test tenant, so running them against a development database is safe.

Worth knowing about two of them:

- `TestOptimality::test_matches_exact_dynamic_program` cross-checks the greedy optimizer
  against an exhaustive dynamic program on 40+ random instances. If you change the
  algorithm, this is the test that tells you whether it is still optimal.
- `test_ifta_net_mode_can_change_the_chosen_station` pins down the behaviour that makes
  the IFTA switch worth having.

## How the savings figure is computed

The headline number is a comparison, so what it is compared against decides what it
means. The baseline models a driver who watches only the gauge: keep rolling while the
next station is still reachable, then fill up right there, whatever it costs.

Two properties keep the figure honest, both locked down by tests:

- **Both plans buy the same gallons.** The baseline's fill is capped at what the rest of
  the trip actually needs. Without that cap it would end the trip with a tank full of
  unburned fuel and "cost" more merely for having bought more — inflating the savings
  into fiction. With it, the two plans price identical fuel and the only difference is
  where it was bought.
- **Identical prices give zero savings.** If every station on the lane charges the same,
  there was no decision to get right, and the product claims no credit.

This baseline is deliberately conservative: a driver who waits until the last possible
station is already doing something sensible. Real overspend — the $500–1500 per truck per
month in the brief — also comes from fuelling wherever is convenient, running low and
taking whatever is nearest, and missing the cheap stop that was 20 miles back. Measured
against that, savings are larger than what this tool reports.

Measured on real routes with the substitute price data:

| Lane | Distance | Stops | Saved |
|---|---|---|---|
| Dallas → Chicago, pump basis | 968 mi | 1 | $21.56 (3.9%) |
| Dallas → Chicago, net basis | 968 mi | 2 | $30.01 (5.8%) |
| Houston → Los Angeles | 1,546 mi | 2 | $58.35 (5.0%) |

The Houston run is the thesis in miniature: it fills up twice in Texas at $5.34 and
crosses Arizona and California — where diesel is around $7 — without buying a drop,
arriving on its reserve.

Expect larger numbers once contract prices are connected: the per-station spread is
modelled at ±$0.15 today, while real negotiated prices differ far more between truck
stops than that.

To change the baseline model, edit `baseline_fuel_plan()` in
`backend/app/services/optimizer/fuel_plan.py` — it is one function, and the invariants
above are enforced by `tests/test_fuel_plan.py`.

## Practical stops

The cheapest plan on paper is not always a plan anyone would drive. On a real
Dallas→Chicago run the optimum bought **0.1 gallons** at one truck stop in order to reach
another one mile down the road that was 13 cents cheaper. Correct to the cent, and
something no driver would ever do.

Two rules keep the output sane, and neither of them is a fudge factor:

- **One interchange is one stop.** Stations within two miles of each other are the same
  stop as far as a driver is concerned, so only the cheapest of them is considered. This
  costs nothing — nobody would ever prefer the dearer of two pumps a mile apart. On the
  run above it removed the absurd stop and made the plan two cents *cheaper*.
- **A stop must be worth the time it takes.** `stop_overhead_usd` (default $8, roughly a
  quarter hour of driver time plus the detour) prices the stop itself. A stop that saves
  less than that is merged away. The guard is measured against the unconstrained optimum,
  never against the previous iteration, so money is only ever given up in proportion to
  the stops the driver no longer has to make — a chain of individually reasonable trades
  cannot add up to an unreasonable total.

Send `"stop_overhead_usd": 0` to get the pure mathematical optimum, token purchases and
all. An earlier attempt used a minimum-gallons threshold instead; it threw away small
purchases at genuinely cheap stations and cost up to 9% — a bad trade when the whole
product saves 3–6%. Pricing the driver's time is the honest version of the same idea.

## Data honesty

The numbers this MVP shows are only as good as their sources, and two of them are
stand-ins. They are labelled everywhere they surface — in `/api/v1/health`, in the API
payloads, and as a banner in the UI.

| Data | Status | To make it real |
|---|---|---|
| Station locations | **Real** — OpenStreetMap export, 1,955 truck-capable stations in 46 states | — |
| Regional diesel prices | **Real** — EIA weekly on-highway diesel averages, public domain | — |
| Per-station price spread | **Modelled** — deterministic ±$0.15 around the regional average | Connect the fuel-card portal |
| Contract prices | **Not available** — every stored price has `is_contract_price=false` | Connect the fuel-card portal |
| Card acceptance | **Modelled** — assumes the major nationwide networks honour the card | Import the card's station list |
| IFTA tax rates | **Placeholder** — approximate, see the header of `backend/app/seeds/ifta_rates.csv` | Load the quarterly [IFTA matrix](https://www.iftach.org/) |
| State boundaries | **Real but coarse** — Natural Earth; river borders sit 1–2 km off | Swap in US Census TIGER before filing IFTA returns |

The regional price differences — the thing the optimizer actually exploits — are real:
the Gulf Coast to California spread is about $1.56/gal, an order of magnitude larger than
the modelled per-station noise.

## Connecting the fuel-card portal

The portal is behind 2FA and the provider has not been named yet, so this part ships as a
working skeleton. Everything that does not depend on the portal is implemented: session
storage and reuse, expiry detection, browser lifecycle, and JSON response capture.

1. Set `CONTRACT_PORTAL_URL` (and optionally the username) in `.env`.
2. Log in once, by hand:
   ```bash
   docker compose exec api python -m app.scrapers.login_cli --provider contract_portal
   ```
   A browser opens; pass 2FA yourself. The session is stored in `scraper_sessions` and
   reused until the portal expires it, at which point the refresh task flags
   `needs_login` instead of failing silently.
3. With the portal's fuel map open, find the JSON request its pins come from and put a
   fragment of that URL in `CONTRACT_PORTAL_MAP_API_PATTERN`.
4. Implement `parse_portal_payload()` in
   `backend/app/scrapers/providers/contract_portal.py` — the only portal-specific code in
   the system — then set `FUEL_PRICE_PROVIDER=contract_portal`.

We do not defeat 2FA programmatically. If the customer can supply a TOTP seed, add a
`pyotp` step to the login CLI; that is a change to one function.

## Beyond this module

The rest of the TZ — CRM, ELD, fuel-card transactions, factoring, HOS, multitenancy and the
production setup — is worked out in [docs/](docs/): stack choices, integration approaches,
risks and the decisions that have to be made before any of it is written. Not
implementation plans; the reasoning behind them.

Start with [docs/README.md](docs/README.md), or jump to
[the production write-up](docs/10-production.md) and
[the roadmap](docs/11-дорожная-карта.md).

## Architecture

```
backend/app/
  services/optimizer/fuel_plan.py   the algorithm — pure functions, no I/O, no ORM
  services/routing/                 RouteProvider interface + GraphHopper
  services/fuel/                    FuelPriceProvider interface + seed / EIA providers
  services/geo/                     corridor query, per-state split, polyline simplification
  services/ifta/                    per-state miles, gallons and tax
  services/planner.py               the one place that knows the whole flow
  scrapers/                         Playwright session handling for portals behind 2FA
  api/v1/                           FastAPI routers
  workers/                          Celery: daily price refresh
frontend/src/                       React SPA: planner, history, trucks, IFTA rates
```

Three seams are deliberate, because each is a known future change:

- `RouteProvider` — GraphHopper Cloud today; self-hosted GraphHopper or HERE later.
- `FuelPriceProvider` — the substitute source today; contract prices later.
- `tenant_id` on every business table — single-tenant today; SaaS later, without a
  migration of every table.

### Spatial notes

Mile markers and corridor distances are computed in EPSG:5070 (US Albers equal-area), not
in lon/lat degrees. In degrees a mile of longitude is shorter than a mile of latitude, so
a diagonal lane like Dallas→Chicago would land mile markers several percent off — enough
to matter when the plan says a station is just within range.

## Not in this MVP

- **HOS (hours of service)**: `route_fuel_stops.stop_type` exists so rest stops can be
  interleaved later, but the FMCSA rules are not implemented.
- **CRM, ELD and factoring integrations**: this module is the foundation they attach to.
- **Multitenancy and billing**: the column is there, the auth is not.
- **Real-time reroute triggers**: `POST /routes/{id}/reroute` is an explicit call, not a
  live traffic subscription.

## Known limitations

- **The truck profile is not active.** Confirmed against the project's own GraphHopper
  key: the account allows only `car`, `bike` and `foot` — truck routing is a paid tier.
  Every route therefore comes back with `truck_legal: false` and a warning, and may ignore
  bridge heights, weight limits and truck-restricted roads. The fuel optimization on top is
  unaffected, but a route must not be handed to a driver until this is resolved, by one of:
  a paid GraphHopper plan; a self-hosted GraphHopper with the truck profile on an OSM
  extract (free, needs ~16 GB RAM); or HERE, whose free tier does include truck routing.
  Any of the three is a new `RouteProvider` subclass and no change anywhere else.
- Detour mileage to a station is reported but not charged against the fuel math; within a
  few-mile corridor it is noise.
- Station coverage comes from OSM tagging, which is uneven. If a lane comes back
  infeasible, widen `corridor_miles` before concluding there is no fuel.
