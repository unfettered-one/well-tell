import { Component, lazy, Suspense } from 'react'
import type { ComponentType, ReactNode } from 'react'
import { ChartNoAxesCombined, Database } from 'lucide-react'
import { visualSchema } from '../../contracts'
import type { DataRow, Visual } from '../../contracts'
import { ResultsTable, DataTable } from './ResultsTable'
import { WellStatusCard } from './WellStatusCard'
import { AreaMonthHeatmap } from './AreaMonthHeatmap'
const WellMap = lazy(() => import('./WellMap'))
const TimeSeriesChart = lazy(() =>
  import('./Charts').then((module) => ({ default: module.TimeSeriesChart })),
)
const ComparisonChart = lazy(() =>
  import('./Charts').then((module) => ({ default: module.ComparisonChart })),
)

const registry: Record<Visual['type'], ComponentType<{ visual: Visual }>> = {
  status_card: WellStatusCard,
  table: ResultsTable,
  line: TimeSeriesChart,
  bar: ComparisonChart,
  map: WellMap,
  heatmap: AreaMonthHeatmap,
}
class VisualBoundary extends Component<
  { children: ReactNode; fallback: (error: string) => ReactNode },
  { error: string | null }
> {
  state = { error: null as string | null }
  static getDerivedStateFromError(error: Error) {
    return { error: error.message || 'The visual could not be rendered safely.' }
  }
  render() {
    return this.state.error ? this.props.fallback(this.state.error) : this.props.children
  }
}
function rawRows(raw: unknown): DataRow[] {
  if (!raw || typeof raw !== 'object' || !('data' in raw) || !Array.isArray(raw.data)) return []
  return raw.data.filter((r): r is DataRow => !!r && typeof r === 'object' && !Array.isArray(r))
}
function Fallback({ reason, data }: { reason: string; data: DataRow[] }) {
  return (
    <div>
      <p className="visual-warning" role="status">
        Visual unavailable: {reason} The answer and citations are unchanged.
      </p>
      <DataTable data={data} />
    </div>
  )
}
export function VisualRenderer({ raw }: { raw: unknown }) {
  if (raw == null) return null
  const parsed = visualSchema.safeParse(raw)
  if (!parsed.success)
    return (
      <section className="visual-panel">
        <Fallback
          reason="The visual specification is malformed or has unsupported mappings."
          data={rawRows(raw)}
        />
      </section>
    )
  const visual = parsed.data,
    Renderer = registry[visual.type]
  return (
    <section className="visual-panel" aria-label={visual.title || `${visual.type} visual`}>
      <div className="visual-heading">
        <ChartNoAxesCombined size={16} aria-hidden="true" />
        <h3>{visual.title || visual.type.replaceAll('_', ' ')}</h3>
        <span>{visual.type.replaceAll('_', ' ')}</span>
      </div>
      {!visual.data.length ? (
        <DataTable data={[]} />
      ) : (
        <VisualBoundary fallback={(reason) => <Fallback reason={reason} data={visual.data} />}>
          <Suspense fallback={<p className="empty-result">Loading visual renderer…</p>}>
            <Renderer visual={visual} />
          </Suspense>
        </VisualBoundary>
      )}
      {visual.result_limit && (
        <p className="result-limit">
          {visual.result_limit.truncated ? 'Limited result · ' : ''}
          {visual.data.length} returned row(s)
          {visual.result_limit.total != null ? ` of ${visual.result_limit.total}` : ''}
          {visual.result_limit.limit != null ? ` · query limit ${visual.result_limit.limit}` : ''}.
          No additional data has been fetched.
        </p>
      )}
      {visual.type !== 'table' && visual.data.length > 0 && (
        <details className="underlying-data">
          <summary>
            <Database size={13} aria-hidden="true" /> View returned data
          </summary>
          <DataTable data={visual.data} columns={visual.columns} />
        </details>
      )}
    </section>
  )
}
