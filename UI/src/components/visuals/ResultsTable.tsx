import type { DataRow, DisplayField, Visual } from '../../contracts'
import { fieldsFor, fieldTitle, formatValue } from './format'

export function DataTable({ data, columns }: { data: DataRow[]; columns?: DisplayField[] | null }) {
  if (!data.length)
    return (
      <p className="empty-result">No rows returned. There is no data to display for this result.</p>
    )
  const fields = fieldsFor(data, columns)
  return (
    <div className="table-scroll" role="region" aria-label="Returned data" tabIndex={0}>
      <table>
        <thead>
          <tr>
            {fields.map((f) => (
              <th key={f.field} scope="col">
                {fieldTitle(f)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i}>
              {fields.map((f) => (
                <td
                  key={f.field}
                  title={typeof row[f.field] === 'number' ? String(row[f.field]) : undefined}
                >
                  {formatValue(row[f.field], f)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
export function ResultsTable({ visual }: { visual: Visual }) {
  return <DataTable data={visual.data} columns={visual.columns} />
}
