import type {
  Health,
  IftaMode,
  IftaRates,
  RouteListItem,
  RoutePlan,
  SavedRoute,
  TruckProfile,
} from './types'

const BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

/** Surfaces the backend's `detail` message instead of a bare status code, because
 *  those messages are written to be actionable ("run the seed command", "set the
 *  API key") and hiding them behind "Request failed" wastes them. */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}/api/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: any) => d.msg).join('; ')
    } catch {
      /* keep the status line */
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export interface PlanInput {
  origin: string
  destination: string
  truck_profile_id?: string
  start_fuel_gallons?: number
  ifta_mode: IftaMode
  corridor_miles: number
}

export const api = {
  health: () => request<Health>('/health'),

  trucks: () => request<TruckProfile[]>('/trucks'),
  createTruck: (payload: Partial<TruckProfile>) =>
    request<TruckProfile>('/trucks', { method: 'POST', body: JSON.stringify(payload) }),
  updateTruck: (id: string, payload: Partial<TruckProfile>) =>
    request<TruckProfile>(`/trucks/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteTruck: (id: string) => request<void>(`/trucks/${id}`, { method: 'DELETE' }),

  plan: (input: PlanInput) =>
    request<RoutePlan>('/routes/plan', {
      method: 'POST',
      body: JSON.stringify({
        origin: { query: input.origin },
        destination: { query: input.destination },
        truck_profile_id: input.truck_profile_id,
        start_fuel_gallons: input.start_fuel_gallons,
        ifta_mode: input.ifta_mode,
        corridor_miles: input.corridor_miles,
        save: true,
      }),
    }),

  routes: () => request<RouteListItem[]>('/routes?limit=100'),
  route: (id: string) => request<SavedRoute>(`/routes/${id}`),

  iftaRates: () => request<IftaRates>('/ifta/rates'),
}
