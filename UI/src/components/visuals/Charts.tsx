import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { DataRow, DisplayField, Visual } from '../../contracts'
import { fieldTitle, formatValue, isNumber } from './format'
const colors = ['#237965', '#c48439', '#6177b2', '#ae6790', '#579caa', '#8b7b45']

export function prepareChart(visual: Visual) {
  if (!visual.x || !visual.y?.length)
    throw new Error('Explicit X-axis and Y-axis mappings were not supplied.')
  const x = visual.x,
    y = visual.y
  if (
    visual.data.some(
      (row) => row[x.field] == null || !['string', 'number'].includes(typeof row[x.field]),
    )
  )
    throw new Error('Some chart rows have no valid X-axis value.')
  if (visual.data.some((row) => y.some((f) => row[f.field] != null && !isNumber(row[f.field]))))
    throw new Error('A mapped measure is not numeric. Values were not converted or guessed.')
  if (y.every((f) => visual.data.every((row) => row[f.field] == null)))
    throw new Error('All mapped measures are missing.')
  let data: DataRow[]
  let measures: { key: string; field: DisplayField; name: string }[]
  if (visual.series) {
    const series = visual.series
    if (
      visual.data.some(
        (row) => row[series] == null || !['string', 'number'].includes(typeof row[series]),
      )
    )
      throw new Error('Some rows have no series label.')
    const groups = [...new Set(visual.data.map((row) => String(row[series])))]
    measures = groups.flatMap((group, gi) =>
      y.map((f, fi) => ({
        key: `measure_${gi}_${fi}`,
        field: f,
        name: `${group} · ${fieldTitle(f)}`,
      })),
    )
    const points = new Map<string, DataRow>(),
      seen = new Set<string>()
    for (const row of visual.data) {
      const key = JSON.stringify(row[x.field]),
        group = String(row[series]),
        pair = JSON.stringify([row[x.field], group])
      if (seen.has(pair))
        throw new Error('Duplicate axis/series pairs require backend aggregation.')
      seen.add(pair)
      const point = points.get(key) || { axis: row[x.field] }
      y.forEach((f, fi) => {
        point[`measure_${groups.indexOf(group)}_${fi}`] = row[f.field] ?? null
      })
      points.set(key, point)
    }
    data = [...points.values()]
  } else {
    if (new Set(visual.data.map((row) => JSON.stringify(row[x.field]))).size !== visual.data.length)
      throw new Error('Duplicate axis values require an explicit series or backend aggregation.')
    measures = y.map((f, i) => ({ key: `measure_${i}`, field: f, name: fieldTitle(f) }))
    data = visual.data.map((row) =>
      Object.fromEntries([
        ['axis', row[x.field]],
        ...y.map((f, i) => [`measure_${i}`, row[f.field] ?? null]),
      ]),
    )
  }
  return { data, measures, x }
}

function Chart({ visual, kind }: { visual: Visual; kind: 'line' | 'bar' }) {
  const { data, measures, x } = prepareChart(visual)
  // Separate axes prevent unlike units from being plotted as if comparable.
  const units = [...new Set(measures.map((m) => m.field.unit || ''))]
  if (units.length > 2)
    throw new Error(
      'More than two different measure units are not supported safely. See the returned table.',
    )
  const common = (
    <>
      <CartesianGrid strokeDasharray="3 4" vertical={false} stroke="#e7ece9" />
      <XAxis
        dataKey="axis"
        tickFormatter={(value) => formatValue(value, x)}
        tick={{ fontSize: 11 }}
        minTickGap={28}
      />
      {units.map((unit, i) => (
        <YAxis
          key={unit}
          yAxisId={unit}
          orientation={i === 0 ? 'left' : 'right'}
          tick={{ fontSize: 11 }}
          width={65}
          label={{ value: unit, angle: -90, position: i === 0 ? 'insideLeft' : 'insideRight' }}
        />
      ))}
      <Tooltip
        labelFormatter={(value) => formatValue(value, x)}
        formatter={(value, name) => {
          const field = measures.find((m) => m.name === name)?.field
          return [`${formatValue(value, field)}${field?.unit ? ` ${field.unit}` : ''}`, name]
        }}
      />
      <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />
    </>
  )
  return (
    <>
      <p className="chart-caption">
        {fieldTitle(x)} · Gaps indicate missing values. Hover or focus chart points to inspect.
      </p>
      <div
        className="chart"
        role="img"
        aria-label={`${visual.type === 'line' ? 'Line' : 'Bar'} chart: ${visual.title || measures.map((m) => m.name).join(', ')}`}
      >
        <ResponsiveContainer width="100%" height={310} minWidth={0}>
          {kind === 'line' ? (
            <LineChart
              data={data}
              accessibilityLayer
              margin={{ top: 20, right: 15, bottom: 12, left: 0 }}
            >
              {common}
              {measures.map((m, i) => (
                <Line
                  key={m.key}
                  dataKey={m.key}
                  name={m.name}
                  yAxisId={m.field.unit || ''}
                  stroke={colors[i % colors.length]}
                  strokeWidth={2.5}
                  dot={data.length < 35}
                  activeDot={{ r: 5 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          ) : (
            <BarChart
              data={data}
              accessibilityLayer
              margin={{ top: 20, right: 15, bottom: 12, left: 0 }}
            >
              {common}
              {measures.map((m, i) => (
                <Bar
                  key={m.key}
                  dataKey={m.key}
                  name={m.name}
                  yAxisId={m.field.unit || ''}
                  fill={colors[i % colors.length]}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={44}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </>
  )
}
export const TimeSeriesChart = ({ visual }: { visual: Visual }) => (
  <Chart visual={visual} kind="line" />
)
export const ComparisonChart = ({ visual }: { visual: Visual }) => (
  <Chart visual={visual} kind="bar" />
)
