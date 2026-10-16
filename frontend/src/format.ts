/** Formatting helpers shared by the pages. Money is always USD — the domain is
 *  the United States — but the number formatting follows the UI language. */
export function makeCurrency(locale: string) {
  const whole = new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD' })
  const cents = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  })
  // Per-gallon prices need three decimals: US pumps price to a tenth of a cent,
  // and rounding them to two hides the differences the optimizer trades on.
  return (value: number) => (Math.abs(value) < 10 ? cents.format(value) : whole.format(value))
}

export function makeNumber(locale: string) {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 })
}

export function hoursMinutes(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60)
  const minutes = Math.round(totalMinutes % 60)
  return `${hours}h ${String(minutes).padStart(2, '0')}m`
}

export function shortDate(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}
