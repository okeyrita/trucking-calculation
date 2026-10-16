import { useTranslation } from 'react-i18next'
import type { StateSegment } from '../types'

interface Props {
  segments: StateSegment[]
  totals?: { owed: number; paid: number; balance: number }
  currency: (value: number) => string
}

export function StateTable({ segments, totals, currency }: Props) {
  const { t } = useTranslation()

  return (
    <section className="panel">
      <h2>{t('ifta.heading')}</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t('ifta.state')}</th>
              <th className="num">{t('ifta.miles')}</th>
              <th className="num">{t('ifta.gallons')}</th>
              <th className="num">{t('ifta.rate')}</th>
              <th className="num">{t('ifta.owed')}</th>
            </tr>
          </thead>
          <tbody>
            {segments.map((segment) => (
              <tr key={segment.state_code}>
                <td className="strong">{segment.state_code}</td>
                <td className="num">{Math.round(segment.miles)}</td>
                <td className="num">{segment.gallons.toFixed(1)}</td>
                <td className="num">{currency(segment.tax_per_gallon)}</td>
                <td className="num">{currency(segment.tax_owed)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totals && (
        <dl className="totals">
          <div>
            <dt>{t('ifta.totalOwed')}</dt>
            <dd>{currency(totals.owed)}</dd>
          </div>
          <div>
            <dt>{t('ifta.paidAtPump')}</dt>
            <dd>{currency(totals.paid)}</dd>
          </div>
          <div>
            <dt>{t('ifta.balance')}</dt>
            <dd className={totals.balance > 0 ? 'negative' : 'positive'}>
              {currency(totals.balance)}
            </dd>
          </div>
        </dl>
      )}
      {totals && <p className="hint">{t('ifta.balanceHint')}</p>}
    </section>
  )
}
