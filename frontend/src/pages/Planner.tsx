import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, ApiError, type PlanInput } from '../api'
import { RouteMap } from '../components/RouteMap'
import { SavingsCard } from '../components/SavingsCard'
import { StateTable } from '../components/StateTable'
import { StopsTable } from '../components/StopsTable'
import { hoursMinutes, makeCurrency, makeNumber } from '../format'
import type { IftaMode, RoutePlan } from '../types'

export function Planner() {
  const { t, i18n } = useTranslation()
  const currency = makeCurrency(i18n.language)
  const numbers = makeNumber(i18n.language)

  const [origin, setOrigin] = useState('Dallas, TX')
  const [destination, setDestination] = useState('Chicago, IL')
  const [truckId, setTruckId] = useState<string>('')
  const [startFuel, setStartFuel] = useState('')
  const [corridor, setCorridor] = useState(3)
  const [iftaMode, setIftaMode] = useState<IftaMode>('pump')
  const [plan, setPlan] = useState<RoutePlan | null>(null)

  const trucks = useQuery({ queryKey: ['trucks'], queryFn: api.trucks })
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })

  const mutation = useMutation({
    mutationFn: (input: PlanInput) => api.plan(input),
    onSuccess: setPlan,
  })

  function submit(event: React.FormEvent) {
    event.preventDefault()
    mutation.mutate({
      origin,
      destination,
      truck_profile_id: truckId || trucks.data?.[0]?.id,
      start_fuel_gallons: startFuel === '' ? undefined : Number(startFuel),
      ifta_mode: iftaMode,
      corridor_miles: corridor,
    })
  }

  function swap() {
    setOrigin(destination)
    setDestination(origin)
  }

  const noApiKey = health.data && !health.data.routing.api_key_configured
  const modelledPrices = health.data && !health.data.fuel_prices.contract_prices

  return (
    <div className="planner">
      {noApiKey && <p className="banner banner-error">{t('banner.noApiKey')}</p>}
      {modelledPrices && <p className="banner banner-warn">{t('banner.modelledPrices')}</p>}

      <form className="panel form" onSubmit={submit}>
        <div className="field grow">
          <label htmlFor="origin">{t('planner.origin')}</label>
          <input
            id="origin"
            value={origin}
            onChange={(event) => setOrigin(event.target.value)}
            placeholder={t('planner.originPlaceholder')}
            required
          />
        </div>

        <button type="button" className="ghost swap" onClick={swap} title={t('planner.swap')}>
          ⇄
        </button>

        <div className="field grow">
          <label htmlFor="destination">{t('planner.destination')}</label>
          <input
            id="destination"
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
            placeholder={t('planner.destinationPlaceholder')}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="truck">{t('planner.truck')}</label>
          <select id="truck" value={truckId} onChange={(event) => setTruckId(event.target.value)}>
            {trucks.data?.map((truck) => (
              <option key={truck.id} value={truck.id}>
                {truck.name} · {truck.mpg} MPG · {truck.tank_gallons} gal
              </option>
            ))}
          </select>
        </div>

        <div className="field narrow">
          <label htmlFor="startFuel">{t('planner.startFuel')}</label>
          <input
            id="startFuel"
            type="number"
            min={0}
            step={1}
            value={startFuel}
            onChange={(event) => setStartFuel(event.target.value)}
            placeholder={t('planner.startFuelHint')}
          />
        </div>

        <div className="field narrow">
          <label htmlFor="corridor">{t('planner.corridor')}</label>
          <input
            id="corridor"
            type="number"
            min={0.5}
            max={50}
            step={0.5}
            value={corridor}
            onChange={(event) => setCorridor(Number(event.target.value))}
          />
        </div>

        <fieldset className="field basis-switch">
          <legend>{t('planner.iftaMode')}</legend>
          <label>
            <input
              type="radio"
              name="ifta"
              checked={iftaMode === 'pump'}
              onChange={() => setIftaMode('pump')}
            />
            {t('planner.pump')}
          </label>
          <label>
            <input
              type="radio"
              name="ifta"
              checked={iftaMode === 'net'}
              onChange={() => setIftaMode('net')}
            />
            {t('planner.net')}
          </label>
        </fieldset>

        <button type="submit" className="primary" disabled={mutation.isPending}>
          {mutation.isPending ? t('planner.building') : t('planner.submit')}
        </button>
      </form>

      <p className="hint indent">{t('planner.iftaHint')}</p>

      {mutation.isError && (
        <p className="banner banner-error">
          {mutation.error instanceof ApiError ? mutation.error.message : t('common.error')}
        </p>
      )}

      {!plan && !mutation.isPending && <p className="empty">{t('results.empty')}</p>}

      {plan && (
        <>
          {plan.warnings.map((warning) => (
            <p key={warning} className="banner banner-warn">
              {warning}
            </p>
          ))}
          {!plan.truck_legal && <p className="banner banner-warn">{t('results.notTruckLegal')}</p>}

          <div className="summary">
            <div>
              <span>{t('results.distance')}</span>
              <strong>{numbers.format(plan.total_miles)} mi</strong>
            </div>
            <div>
              <span>{t('results.driveTime')}</span>
              <strong>{hoursMinutes(plan.total_minutes)}</strong>
            </div>
            <div>
              <span>{t('results.stops')}</span>
              <strong>{plan.stops.length}</strong>
            </div>
            <div>
              <span>{t('results.gallons')}</span>
              <strong>{numbers.format(plan.total_gallons)}</strong>
            </div>
            <div>
              <span>{t('results.fuelCost')}</span>
              <strong>{currency(plan.total_fuel_cost)}</strong>
            </div>
            <div>
              <span>{t('results.arrival')}</span>
              <strong>{numbers.format(plan.arrival_gallons)} gal</strong>
            </div>
          </div>

          <div className="two-col">
            <section className="panel map-panel">
              <RouteMap
                geometry={plan.geometry.coordinates}
                stops={plan.stops}
                currency={currency}
              />
            </section>
            <SavingsCard savings={plan.savings} currency={currency} />
          </div>

          <section className="panel">
            <h2>
              {t('results.heading')}{' '}
              <small className="muted">
                {t('results.considered', { count: plan.candidates_considered })}
              </small>
            </h2>
            {plan.feasible ? (
              <StopsTable stops={plan.stops} basis={plan.savings.basis} currency={currency} />
            ) : (
              <p className="banner banner-error">
                <strong>{t('results.infeasible')}</strong> — {plan.infeasible_reason}
              </p>
            )}
          </section>

          <StateTable
            segments={plan.ifta.segments}
            totals={{
              owed: plan.ifta.total_tax_owed,
              paid: plan.ifta.tax_paid_at_pump,
              balance: plan.ifta.net_balance,
            }}
            currency={currency}
          />
        </>
      )}
    </div>
  )
}
