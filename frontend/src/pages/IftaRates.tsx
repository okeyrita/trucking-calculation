import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import { makeCurrency } from '../format'

export function IftaRates() {
  const { t, i18n } = useTranslation()
  const currency = makeCurrency(i18n.language)
  const rates = useQuery({ queryKey: ['ifta'], queryFn: api.iftaRates })

  if (rates.isLoading) return <p className="empty">{t('common.loading')}</p>
  if (rates.isError || !rates.data) return <p className="banner banner-error">{t('common.error')}</p>

  const sorted = [...rates.data.rates].sort((a, b) => b.tax_per_gallon - a.tax_per_gallon)

  return (
    <section className="panel">
      <h2>{t('iftaPage.heading')}</h2>
      {/* The API ships this disclaimer with the data; showing it is the point. */}
      <p className="banner banner-warn">{rates.data.disclaimer}</p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t('iftaPage.state')}</th>
              <th className="num">{t('iftaPage.rate')}</th>
              <th>{t('iftaPage.from')}</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((rate) => (
              <tr key={rate.state_code}>
                <td className="strong">{rate.state_code}</td>
                <td className="num">{currency(rate.tax_per_gallon)}</td>
                <td className="muted">{rate.effective_from}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
