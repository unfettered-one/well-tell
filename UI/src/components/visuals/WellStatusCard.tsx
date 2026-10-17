import type { Visual } from '../../contracts'
import { fieldsFor, fieldTitle, formatValue } from './format'

export function WellStatusCard({ visual }: { visual: Visual }) {
  if (visual.data.length !== 1) throw new Error('A status card requires exactly one returned well.')
  const row = visual.data[0]
  // Display the backend's explicit classification, never derive it from readings.
  const producing = row.is_producing
  const returnedStatus = row.production_status ?? row.status
  const status =
    producing === 1 || producing === true
      ? 'Producing'
      : producing === 0 || producing === false
        ? 'Not producing'
        : typeof returnedStatus === 'string'
          ? returnedStatus
          : 'Status not supplied'
  return (
    <div className="status-card">
      <div className="status-top">
        <div>
          <span className="eyebrow">Well status</span>
          <h3>{formatValue(row.well_name ?? row.asset_id ?? row.well_id)}</h3>
        </div>
        <span
          className={`status-pill ${producing === 1 || producing === true ? 'positive' : 'neutral'}`}
        >
          <span aria-hidden="true">●</span> {status}
        </span>
      </div>
      <dl className="status-details">
        {fieldsFor(visual.data, visual.columns).map((f) => (
          <div key={f.field}>
            <dt>{fieldTitle(f)}</dt>
            <dd title={typeof row[f.field] === 'number' ? String(row[f.field]) : undefined}>
              {formatValue(row[f.field], f)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
