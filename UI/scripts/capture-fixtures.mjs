// Test-only snapshots. Never imported by the live application.
// Use --live after scripts/verify_ui_live.py for unmodified fresh responses.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
const live = process.argv.includes('--live')
const source = live ? '../data/ui-live-results.json' : '../data/eval-final-results.json'
const results = JSON.parse(
  readFileSync(new URL(source.replace('../', '../../'), import.meta.url), 'utf8'),
)
const cases = { status_card: 'Q1', table: 'Q2', line: 'Q3', bar: 'Q6', map: 'Q7', heatmap: 'Q8' }
const captures = {}
for (const [type, id] of Object.entries(cases)) {
  const entry = results.find((r) => (live ? r.case === type : r.case === id))
  if (!entry || entry.status !== 200) throw new Error(`No successful capture for ${type}`)
  const response = structuredClone(entry.response)
  if (!live) {
    // Historical records predate typed mappings. Annotations add display metadata
    // only; no SQL data, answer, units or business values are fabricated.
    const v = response.visual
    if (type === 'line') {
      v.x = { field: 'inspected_at', label: 'Inspection', format: 'date' }
      v.y = ['wellhead_temp_c', 'ambient_temp_c'].map((field) => ({
        field,
        label: field,
        unit: '°C',
        format: 'number',
      }))
    }
    if (type === 'bar') {
      v.x = { field: 'asset_id', label: 'Well' }
      v.y = [{ field: 'downtime_days', label: 'Downtime', unit: 'days', format: 'number' }]
    }
    if (type === 'map') {
      v.latitude = 'lat'
      v.longitude = 'lon'
      v.well_id = 'asset_id'
    }
    if (type === 'heatmap') {
      delete v.x
      delete v.y
      v.row = { field: 'area_name', label: 'Area' }
      v.column = { field: 'month', label: 'Month' }
      v.value = { field: 'spill_count', label: 'Spills', format: 'number' }
    }
  }
  captures[type] = response
}
const output = new URL('../src/test/fixtures/captured-responses.json', import.meta.url)
mkdirSync(new URL('.', output), { recursive: true })
writeFileSync(
  output,
  JSON.stringify(
    {
      provenance: { source, captured: true, displayMetadataAnnotated: !live },
      responses: captures,
    },
    null,
    2,
  ) + '\n',
)
