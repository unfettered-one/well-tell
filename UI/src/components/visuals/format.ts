import type { DataRow, DisplayField } from '../../contracts'

export const label = (f: DisplayField) => f.label || f.field.replaceAll('_', ' ')
export const fieldTitle = (f: DisplayField) => `${label(f)}${f.unit ? ` (${f.unit})` : ''}`
export function formatValue(value: unknown, field?: DisplayField): string {
  if (value === null || value === undefined || value === '') return 'Not available'
  if (field?.format === 'date' || field?.format === 'datetime') {
    const date = new Date(String(value))
    if (!Number.isNaN(date.getTime()))
      return new Intl.DateTimeFormat('en', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        timeZone: 'UTC',
        ...(field.format === 'datetime'
          ? { hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }
          : {}),
      }).format(date)
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'Not available'
    return (
      new Intl.NumberFormat('en', {
        maximumFractionDigits: field?.decimals ?? 2,
        ...(field?.decimals != null ? { minimumFractionDigits: field.decimals } : {}),
      }).format(value) + (field?.format === 'percent' ? '%' : '')
    )
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}
export function fieldsFor(data: DataRow[], columns?: DisplayField[] | null): DisplayField[] {
  return columns?.length
    ? columns
    : [...new Set(data.flatMap((row) => Object.keys(row)))].map((field) => ({ field }))
}
export const isNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)
