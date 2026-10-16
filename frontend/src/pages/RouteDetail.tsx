import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { RouteMap } from '../components/RouteMap'
import { StateTable } from '../components/StateTable'
import { StopsTable } from '../components/StopsTable'
import { hoursMinutes, makeCurrency, makeNumber, shortDate } from '../format'

export function RouteDetail() {
  const { routeId = '' } = useParams()
  const { t, i18n } = useTranslation()
  const currency = makeCurrency(i18n.language)
  const numbers = makeNumber(i18n.language)

  const route = useQuery({ queryKey: ['route', routeId], queryFn: () => api.route(routeId) })

  if (route.isLoading) return <p className="empty">{t('common.loading')}</p>
  if (route.isError || !route.data) return <p className="banner banner-error">{t('common.error')}</p>

  const saved = route.data
  const savingsPct = saved.baseline_cost > 0 ? (saved.savings_usd / saved.baseline_cost) * 100 : 0

  return (
    <div className="planner">
      <p className="breadcrumbs">
        <Link to="/history">← {t('nav.history')}</Link>
        <span className="muted"> · {shortDate(saved.created_at, i18n.language)}</span>
      </p>

      <h2>
        {saved.origin_label} → {saved.destination_label}
      </h2>

      {saved.warnings.map((warning) => (
        <p key={warning} className="banner banner-warn">
          {warning}
        </p>
      ))}

      <div className="summary">
        <div>
          <span>{t('results.distance')}</span>
          <strong>{numbers.format(saved.total_miles)} mi</strong>
        </div>
        <div>
          <span>{t('results.driveTime')}</span>
          <strong>{hoursMinutes(saved.total_minutes)}</strong>
        </div>
        <div>
          <span>{t('results.stops')}</span>
          <strong>{saved.stops.length}</strong>
        </div>
        <div>
          <span>{t('results.fuelCost')}</span>
          <strong>{currency(saved.total_fuel_cost)}</strong>
        </div>
        <div>
          <span>{t('results.baseline')}</span>
          <strong>{currency(saved.baseline_cost)}</strong>
        </div>
        <div>
          <span>{t('results.savings')}</span>
          <strong className="positive">
            {currency(saved.savings_usd)} ({savingsPct.toFixed(1)}%)
          </strong>
        </div>
      </div>

      <section className="panel map-panel">
        <RouteMap geometry={saved.geometry.coordinates} stops={saved.stops} currency={currency} />
      </section>

      <section className="panel">
        <h2>{t('results.heading')}</h2>
        <StopsTable stops={saved.stops} basis={saved.ifta_mode} currency={currency} />
      </section>

      <StateTable segments={saved.state_segments} currency={currency} />
    </div>
  )
}
