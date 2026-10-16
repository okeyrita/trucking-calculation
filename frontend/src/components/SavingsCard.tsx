import { useTranslation } from 'react-i18next'
import type { Savings } from '../types'

/** The number the whole product exists to produce, so it gets the largest type
 *  on the page and an explicit statement of what it is compared against. */
export function SavingsCard({ savings, currency }: { savings: Savings; currency: (v: number) => string }) {
  const { t } = useTranslation()
  const positive = savings.savings_usd > 0.005

  return (
    <section className={`savings ${positive ? 'savings-positive' : 'savings-neutral'}`}>
      <header>
        <h2>{t('results.savings')}</h2>
      </header>
      <p className="savings-amount">
        {currency(savings.savings_usd)}
        <small>
          {savings.savings_pct.toFixed(1)}% · {t('results.perTrip')}
        </small>
      </p>
      <dl className="savings-compare">
        <div>
          <dt>{t('results.baseline')}</dt>
          <dd>{currency(savings.baseline_cost)}</dd>
        </div>
        <div>
          <dt>{t('results.optimized')}</dt>
          <dd>{currency(savings.optimized_cost)}</dd>
        </div>
      </dl>
      <p className="hint">{savings.baseline_description}</p>
    </section>
  )
}
