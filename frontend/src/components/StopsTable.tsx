import { useTranslation } from 'react-i18next'
import type { FuelStop, IftaMode } from '../types'

interface Props {
  stops: FuelStop[]
  basis: IftaMode
  currency: (value: number) => string
}

export function StopsTable({ stops, basis, currency }: Props) {
  const { t } = useTranslation()

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>{t('table.seq')}</th>
            <th>{t('table.station')}</th>
            <th>{t('table.state')}</th>
            <th className="num">{t('table.mile')}</th>
            <th className="num">{t('table.detour')}</th>
            <th className="num">{t('table.buy')}</th>
            {/* The column the plan was optimized on is highlighted, so it is
                obvious which price drove the decision. */}
            <th className={`num ${basis === 'pump' ? 'basis' : ''}`}>{t('table.price')}</th>
            <th className={`num ${basis === 'net' ? 'basis' : ''}`}>{t('table.netPrice')}</th>
            <th className="num">{t('table.cost')}</th>
            <th className="num">{t('table.arriveWith')}</th>
            <th className="num">{t('table.leaveWith')}</th>
          </tr>
        </thead>
        <tbody>
          {stops.map((stop) => (
            <tr key={stop.seq}>
              <td>{stop.seq}</td>
              <td>{stop.name}</td>
              <td>{stop.state}</td>
              <td className="num">{Math.round(stop.mile_marker)}</td>
              <td className="num">{stop.detour_miles.toFixed(1)}</td>
              <td className="num strong">{stop.gallons.toFixed(0)}</td>
              <td className={`num ${basis === 'pump' ? 'basis' : ''}`}>
                {currency(stop.price_per_gallon)}
              </td>
              <td className={`num ${basis === 'net' ? 'basis' : ''}`}>
                {currency(stop.net_price_per_gallon)}
              </td>
              <td className="num">{currency(stop.cost)}</td>
              <td className="num muted">{stop.arrival_gallons.toFixed(0)}</td>
              <td className="num muted">{stop.departure_gallons.toFixed(0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
