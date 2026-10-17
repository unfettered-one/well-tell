import { z } from 'zod'

export const displayFieldSchema = z
  .object({
    field: z.string().min(1),
    label: z.string().nullable().optional(),
    unit: z.string().nullable().optional(),
    format: z.enum(['text', 'number', 'date', 'datetime', 'percent']).nullable().optional(),
    decimals: z.number().int().min(0).max(10).nullable().optional(),
  })
  .strict()
const rowSchema = z.record(z.string(), z.unknown())
export const visualSchema = z
  .object({
    type: z.enum(['status_card', 'table', 'line', 'bar', 'map', 'heatmap']),
    title: z.string().nullable().optional(),
    data: z.array(rowSchema),
    columns: z.array(displayFieldSchema).nullable().optional(),
    x: displayFieldSchema.nullable().optional(),
    y: z.array(displayFieldSchema).min(1).nullable().optional(),
    series: z.string().nullable().optional(),
    latitude: z.string().nullable().optional(),
    longitude: z.string().nullable().optional(),
    well_id: z.string().nullable().optional(),
    row: displayFieldSchema.nullable().optional(),
    column: displayFieldSchema.nullable().optional(),
    value: displayFieldSchema.nullable().optional(),
    result_limit: z
      .object({
        truncated: z.boolean().optional(),
        total: z.number().int().nonnegative().nullable().optional(),
        limit: z.number().int().nonnegative().nullable().optional(),
      })
      .nullable()
      .optional(),
  })
  .passthrough()
  .superRefine((v, ctx) => {
    const names = [
      ...(v.columns || []),
      ...(v.y || []),
      ...[v.x, v.row, v.column, v.value].filter((f) => f != null),
    ].map((f) => f.field)
    names.push(...[v.series, v.latitude, v.longitude, v.well_id].filter((f): f is string => !!f))
    if (v.data.length && names.some((name) => !v.data.some((row) => Object.hasOwn(row, name)))) {
      ctx.addIssue({
        code: 'custom',
        message: 'A display mapping refers to a field not returned by the backend.',
      })
    }
  })

// Read older explicit x/y string mappings without inferring roles from data.
// Ambiguous legacy visuals remain safely unrenderable and show their table.
export function normalizeLegacyVisual(raw: unknown): unknown {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return raw
  const visual = { ...raw } as Record<string, unknown>
  if (visual.type === 'heatmap') {
    if (typeof visual.x === 'string') {
      visual.column ??= { field: visual.x }
      delete visual.x
    }
    if (typeof visual.y === 'string') {
      visual.row ??= { field: visual.y }
      delete visual.y
    }
    if (typeof visual.value === 'string') visual.value = { field: visual.value }
  } else {
    if (typeof visual.x === 'string') visual.x = { field: visual.x }
    if (typeof visual.y === 'string') visual.y = [{ field: visual.y }]
    else if (Array.isArray(visual.y)) {
      visual.y = visual.y.map((field) => (typeof field === 'string' ? { field } : field))
    }
  }
  return visual
}
export type DisplayField = z.infer<typeof displayFieldSchema>
export type Visual = z.infer<typeof visualSchema>
export type DataRow = Record<string, unknown>

// Validate the envelope independently: a bad visual must never hide an answer.
export const answerSchema = z.object({
  session_id: z.string().min(1),
  answer: z.string(),
  citations: z.array(z.string()),
  visual: z.unknown().optional(),
  tool_calls: z.array(z.object({ name: z.string(), status: z.string() })),
})
export type Answer = z.infer<typeof answerSchema>
export const healthSchema = z.object({
  status: z.string(),
  datasets: z.array(
    z.object({
      dataset_id: z.string(),
      wells: z.number(),
      as_of: z.string().nullable().optional(),
      users: z.array(
        z.object({ user_id: z.string(), name: z.string().nullable(), role: z.string().nullable() }),
      ),
    }),
  ),
})
export type Dataset = z.infer<typeof healthSchema>['datasets'][number]
