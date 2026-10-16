// Mirrors the backend's Pydantic schemas. Units are US customary throughout:
// miles, gallons, USD, and MPG (miles per gallon — the inverse of L/100km).

export type IftaMode = 'pump' | 'net'

export interface TruckProfile {
  id: string
  name: string
  mpg: number
  tank_gallons: number
  reserve_fraction: number
  height_m: number
  width_m: number
  length_m: number
  weight_kg: number
  axles: number
  usable_gallons: number
  range_miles: number
}

export interface FuelStop {
  seq: number
  station_id: string | null
  name: string
  state: string
  lat: number | null
  lon: number | null
  mile_marker: number
  detour_miles: number
  gallons: number
  price_per_gallon: number
  net_price_per_gallon: number
  cost: number
  arrival_gallons: number
  departure_gallons: number
}

export interface StateSegment {
  state_code: string
  miles: number
  gallons: number
  tax_per_gallon: number
  tax_owed: number
}

export interface Savings {
  optimized_cost: number
  baseline_cost: number
  savings_usd: number
  savings_pct: number
  basis: IftaMode
  baseline_description: string
}

export interface RoutePlan {
  route_id: string | null
  origin_label: string
  destination_label: string
  total_miles: number
  total_minutes: number
  geometry: { type: 'LineString'; coordinates: [number, number][] }
  profile_used: string
  truck_legal: boolean
  feasible: boolean
  infeasible_reason: string | null
  total_gallons: number
  total_fuel_cost: number
  arrival_gallons: number
  stops: FuelStop[]
  candidates_considered: number
  savings: Savings
  ifta: {
    mode: IftaMode
    segments: StateSegment[]
    total_tax_owed: number
    tax_paid_at_pump: number
    net_balance: number
  }
  warnings: string[]
}

export interface RouteListItem {
  id: string
  origin_label: string
  destination_label: string
  total_miles: number
  total_minutes: number
  ifta_mode: string
  total_fuel_cost: number
  baseline_cost: number
  savings_usd: number
  feasible: boolean
  created_at: string
}

export interface SavedRoute {
  id: string
  created_at: string
  origin_label: string
  destination_label: string
  origin: [number, number]
  destination: [number, number]
  total_miles: number
  total_minutes: number
  geometry: { type: 'LineString'; coordinates: [number, number][] }
  ifta_mode: IftaMode
  corridor_miles: number
  start_fuel_gallons: number
  feasible: boolean
  total_gallons: number
  total_fuel_cost: number
  baseline_cost: number
  savings_usd: number
  stops: FuelStop[]
  state_segments: StateSegment[]
  warnings: string[]
}

export interface IftaRates {
  fuel_type: string
  count: number
  rates: { state_code: string; tax_per_gallon: number; effective_from: string }[]
  disclaimer: string
}

export interface Health {
  status: string
  checks: Record<string, unknown>
  routing: { provider: string; api_key_configured: boolean; truck_profile_requested: boolean }
  fuel_prices: { provider: string; contract_prices: boolean }
}
