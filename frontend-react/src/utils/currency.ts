export const CURRENCY_MAP: Record<string, { symbol: string; label: string }> = {
  CNY: { symbol: '¥', label: '元' },
  RUB: { symbol: '₽', label: '₽' },
  USD: { symbol: '$', label: '$' },
  EUR: { symbol: '€', label: '€' },
}

/** Get currency display info from a currency code string. */
export function getCurrencyInfo(currencyCode?: string | null): { symbol: string; label: string } {
  const code = (currencyCode || 'CNY').toUpperCase()
  return CURRENCY_MAP[code] || { symbol: code, label: code }
}

/** Format a price value with currency symbol: "¥ 100.48" or "₽ 1,234" */
export function formatPrice(
  price: number | string | null | undefined,
  currencyCode?: string | null,
): string {
  if (price == null) return '—'
  const { symbol } = getCurrencyInfo(currencyCode)
  return `${symbol} ${Number(price).toLocaleString()}`
}

/** Format price for display in table cells, 2 decimal places */
export function formatPriceFixed(
  price: number | string | null | undefined,
  currencyCode?: string | null,
): string {
  if (price == null) return '—'
  const { symbol } = getCurrencyInfo(currencyCode)
  return `${symbol} ${Number(price).toFixed(2)}`
}

/** Render a price suffix/addon for InputNumber */
export function priceSuffix(currencyCode?: string | null): string {
  return getCurrencyInfo(currencyCode).symbol
}
