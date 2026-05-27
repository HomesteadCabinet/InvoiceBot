function normalizeNumericInput(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }

  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
}

function trimTrailingZeros(value, maxFractionDigits = 4) {
  const numericValue = normalizeNumericInput(value)
  if (numericValue === null) {
    return null
  }

  const fixed = numericValue.toFixed(maxFractionDigits)
  return fixed
    .replace(/(\.\d*?[1-9])0+$/u, '$1')
    .replace(/\.0+$/u, '')
    .replace(/\.$/u, '')
}

export function formatNumberValue(value, maxFractionDigits = 4) {
  const trimmed = trimTrailingZeros(value, maxFractionDigits)
  if (trimmed === null) {
    return '—'
  }
  return Number(trimmed).toLocaleString(undefined, {
    maximumFractionDigits: maxFractionDigits,
  })
}

export function formatCurrencyUSD(value) {
  const numericValue = normalizeNumericInput(value)
  if (numericValue === null) {
    return '—'
  }

  const formatted = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numericValue)

  return formatted
}

export function formatTypedValue(value, type) {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  if (type === 'currency') {
    return formatCurrencyUSD(value)
  }

  if (type === 'number') {
    return formatNumberValue(value)
  }

  return String(value)
}
