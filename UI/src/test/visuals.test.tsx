import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect } from 'vitest'
import captures from './fixtures/captured-responses.json'
import { VisualRenderer } from '../components/visuals/VisualRenderer'
import { prepareChart } from '../components/visuals/Charts'
import { visualSchema } from '../contracts'
import { formatValue } from '../components/visuals/format'

describe('real-response visual registry', () => {
  it.each(Object.entries(captures.responses))(
    'validates the captured %s contract and renders its title',
    async (_, response) => {
      expect(visualSchema.safeParse(response.visual).success).toBe(true)
      render(<VisualRenderer raw={response.visual} />)
      expect(screen.getByRole('heading', { name: response.visual.title })).toBeInTheDocument()
      await waitFor(() =>
        expect(screen.queryByText('Loading visual renderer…')).not.toBeInTheDocument(),
      )
      expect(screen.queryByText(/Visual unavailable:/)).not.toBeInTheDocument()
      if (response.visual.type === 'map')
        expect(screen.getByText('OpenStreetMap')).toBeInTheDocument()
    },
  )

  it('keeps raw data visible when mappings are malformed', () => {
    render(
      <VisualRenderer
        raw={{ type: 'line', x: { field: 'invented' }, data: [{ asset_id: 'WELL-1234', days: 7 }] }}
      />,
    )
    expect(screen.getByText(/Visual unavailable:/)).toBeInTheDocument()
    expect(screen.getByText('WELL-1234')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })
  it('falls back instead of guessing an unmapped numeric axis', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<VisualRenderer raw={{ type: 'line', data: [{ days: 7, temperature: 41 }] }} />)
    expect(await screen.findByText(/Explicit X-axis and Y-axis mappings/)).toBeInTheDocument()
    expect(screen.getAllByText('41').length).toBeGreaterThan(0)
  })
  it.each(['status_card', 'table', 'line', 'bar', 'map', 'heatmap'])(
    'shows an honest empty %s state',
    (type) => {
      render(<VisualRenderer raw={{ type, data: [] }} />)
      expect(screen.getByText(/No rows returned/)).toBeInTheDocument()
      expect(screen.queryByRole('img')).not.toBeInTheDocument()
    },
  )
  it('uses null gaps, not zero, and rejects implicit aggregation', () => {
    const visual = visualSchema.parse({
      type: 'line',
      x: { field: 'date' },
      y: [{ field: 'temp' }],
      data: [
        { date: 'A', temp: 41 },
        { date: 'B', temp: null },
      ],
    })
    expect(prepareChart(visual).data[1].measure_0).toBeNull()
    expect(() => prepareChart({ ...visual, data: [...visual.data, visual.data[0]] })).toThrow(
      /Duplicate/,
    )
  })
  it('pivots explicit series without summing or inventing missing measurements', () => {
    const visual = visualSchema.parse({
      type: 'line',
      x: { field: 'date' },
      y: [{ field: 'temp' }],
      series: 'well',
      data: [
        { date: 'A', well: 'W1', temp: 41 },
        { date: 'A', well: 'W2', temp: null },
        { date: 'B', well: 'W2', temp: 32 },
      ],
    })
    const { data, measures } = prepareChart(visual)
    expect(measures).toHaveLength(2)
    expect(data[0].measure_1_0).toBeNull()
    expect(data[1].measure_0_0).toBeUndefined()
  })
  it('lets users inspect missing heatmap cells, without treating them as zero', () => {
    render(
      <VisualRenderer
        raw={{
          type: 'heatmap',
          row: { field: 'area' },
          column: { field: 'month' },
          value: { field: 'count' },
          data: [
            { area: 'North', month: '2026-10', count: null },
            { area: 'South', month: '2026-10', count: 0 },
          ],
        }}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'North, 2026-10: Not available' }))
    expect(screen.getByRole('status')).toHaveTextContent('Not available')
    expect(screen.getByRole('button', { name: 'South, 2026-10: 0' })).toBeInTheDocument()
  })
  it('shows result limits exactly as supplied', () => {
    render(
      <VisualRenderer
        raw={{
          type: 'table',
          data: [{ well: 'A' }],
          result_limit: { truncated: true, limit: 1, total: 10 },
        }}
      />,
    )
    expect(screen.getByText(/Limited result · 1 returned row\(s\) of 10/)).toBeInTheDocument()
  })
  it('formats without changing raw values or multiplying percentages', () => {
    expect(formatValue(null)).toBe('Not available')
    expect(formatValue(0)).toBe('0')
    expect(formatValue(4.123456, { field: 'temp', decimals: 2 })).toBe('4.12')
    expect(formatValue(20, { field: 'pct', format: 'percent' })).toBe('20%')
  })
  it('displays an explicit text production status without deriving a threshold', () => {
    render(
      <VisualRenderer
        raw={{
          type: 'status_card',
          data: [{ asset_id: 'WELL-0042', production_status: 'Producing', eff_temp_delta_c: null }],
        }}
      />,
    )
    expect(screen.getByText('Producing', { selector: '.status-pill' })).toBeInTheDocument()
  })
  it('does not derive a production status from temperature', () => {
    render(
      <VisualRenderer
        raw={{ type: 'status_card', data: [{ asset_id: 'WELL-0042', eff_temp_delta_c: 70 }] }}
      />,
    )
    expect(screen.getByText('Status not supplied')).toBeInTheDocument()
  })
  it('shows fallback data when coordinates are missing rather than inventing locations', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <VisualRenderer
        raw={{
          type: 'map',
          latitude: 'lat',
          longitude: 'lon',
          data: [{ asset_id: 'WELL-0042', lat: null, lon: null }],
        }}
      />,
    )
    expect(await screen.findByText(/No valid coordinates/)).toBeInTheDocument()
    expect(screen.queryByText('OpenStreetMap')).not.toBeInTheDocument()
  })
})
