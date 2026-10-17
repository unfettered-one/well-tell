import { useState } from 'react'
import type { DataRow, Visual } from '../../contracts'
import { fieldTitle, formatValue, isNumber } from './format'

export function AreaMonthHeatmap({ visual }: { visual: Visual }) {
  const [selected, setSelected] = useState<DataRow | null>(null)
  const { row, column, value } = visual
  if (!row || !column || !value)
    throw new Error('Explicit row, column and numeric value mappings are required.')
  const cells = new Map<string, DataRow>(),
    rows: unknown[] = [],
    cols: unknown[] = []
  for (const datum of visual.data) {
    if (datum[row.field] == null || datum[column.field] == null)
      throw new Error('A heatmap row or column label is missing.')
    if (datum[value.field] != null && !isNumber(datum[value.field]))
      throw new Error('Heatmap values must be numeric or missing.')
    const key = JSON.stringify([datum[row.field], datum[column.field]])
    if (cells.has(key)) throw new Error('Duplicate heatmap cells need backend aggregation.')
    cells.set(key, datum)
    if (!rows.includes(datum[row.field])) rows.push(datum[row.field])
    if (!cols.includes(datum[column.field])) cols.push(datum[column.field])
  }
  const values = visual.data.map((d) => d[value.field]).filter(isNumber)
  const min = Math.min(...values),
    max = Math.max(...values)
  return (
    <div>
      <p className="chart-caption">
        {fieldTitle(value)} · Select a cell to inspect returned data. Hatched cells have no value.
      </p>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Heatmap">
        <table className="heatmap">
          <thead>
            <tr>
              <th scope="col">
                {fieldTitle(row)} / {fieldTitle(column)}
              </th>
              {cols.map((c, i) => (
                <th key={i} scope="col">
                  {formatValue(c, column)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri}>
                <th scope="row">{formatValue(r, row)}</th>
                {cols.map((c, ci) => {
                  const datum = cells.get(JSON.stringify([r, c])),
                    n = datum?.[value.field],
                    valid = isNumber(n)
                  const intensity = valid
                    ? max === min
                      ? 0.6
                      : 0.15 + (0.75 * (n - min)) / (max - min)
                    : 0
                  return (
                    <td key={ci}>
                      <button
                        type="button"
                        className={`heat-cell ${!valid ? 'missing' : ''}`}
                        style={
                          valid
                            ? {
                                backgroundColor: `rgba(35,121,101,${intensity})`,
                                color: intensity > 0.55 ? '#fff' : '#18392e',
                              }
                            : {}
                        }
                        aria-label={`${formatValue(r, row)}, ${formatValue(c, column)}: ${formatValue(n, value)}`}
                        onClick={() =>
                          setSelected(
                            datum || { [row.field]: r, [column.field]: c, [value.field]: null },
                          )
                        }
                      >
                        {valid ? formatValue(n, value) : '—'}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="heatmap-legend">
        Lower <span aria-hidden="true" /> Higher ·{' '}
        {values.length
          ? `${formatValue(min, value)} – ${formatValue(max, value)} ${value.unit || ''}`
          : 'No numeric values returned'}
      </p>
      {selected && (
        <p className="cell-detail" role="status">
          {formatValue(selected[row.field], row)} · {formatValue(selected[column.field], column)}:{' '}
          <strong>
            {formatValue(selected[value.field], value)}{' '}
            {selected[value.field] != null ? value.unit : ''}
          </strong>
        </p>
      )}
    </div>
  )
}
