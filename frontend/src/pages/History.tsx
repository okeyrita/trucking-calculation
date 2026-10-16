import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { makeCurrency, makeNumber, shortDate } from '../format'

export function History() {
  const { t, i18n } = useTranslation()
  const currency = makeCurrency(i18n.language)
  const numbers = makeNumber(i18n.language)
  const routes = useQuery({ queryKey: ['routes'], queryFn: api.routes })

  if (routes.isLoading) return <p className="empty">{t('common.loading')}</p>
  if (routes.isError) return <p className="banner banner-error">{t('common.error')}</p>

  return (
    <section className="panel">
      <h2>{t('history.heading')}</h2>
      {routes.data && routes.data.length === 0 && <p className="empty">{t('history.empty')}</p>}
      {routes.data && routes.data.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('history.when')}</th>
                <th>{t('history.lane')}</th>
                <th className="num">{t('history.miles')}</th>
                <th className="num">{t('history.cost')}</th>
                <th className="num">{t('history.saved')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {routes.data.map((route) => (
                <tr key={route.id} className={route.feasible ? '' : 'row-warn'}>
                  <td className="muted">{shortDate(route.created_at, i18n.language)}</td>
                  <td className="strong">
                    {route.origin_label} → {route.destination_label}
                  </td>
                  <td className="num">{numbers.format(route.total_miles)}</td>
                  <td className="num">{currency(route.total_fuel_cost)}</td>
                  <td className="num positive">{currency(route.savings_usd)}</td>
                  <td>
                    <Link to={`/routes/${route.id}`}>{t('history.open')}</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
