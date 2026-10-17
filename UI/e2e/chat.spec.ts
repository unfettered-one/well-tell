import { test, expect } from '@playwright/test'
import captures from '../src/test/fixtures/captured-responses.json' with { type: 'json' }

test('captured real responses render all six visuals, follow-up context and identity isolation', async ({
  page,
}) => {
  const requests: Record<string, unknown>[] = []
  const responses = Object.values(captures.responses)
  await page.route('**/health', (route) =>
    route.fulfill({
      json: {
        status: 'ok',
        datasets: [
          {
            dataset_id: 'sample',
            wells: 200,
            as_of: '2026-10-16',
            users: [
              { user_id: 'U-201', name: 'Michael Turner', role: 'inspector' },
              { user_id: 'U-202', name: 'Jessica Reed', role: 'inspector' },
            ],
          },
          {
            dataset_id: 'test',
            wells: 1,
            as_of: '2025-01-02',
            users: [{ user_id: 'U-301', name: 'Demo test user', role: 'inspector' }],
          },
        ],
      },
    }),
  )
  await page.route('**/ready', (route) => route.fulfill({ json: { ready: true } }))
  // Tile availability is deliberately not assumed; test the explicit fallback.
  await page.route('**/*.tile.openstreetmap.org/**', (route) => route.abort())
  await page.route('**/chat', async (route) => {
    requests.push(route.request().postDataJSON())
    await route.fulfill({
      json: {
        ...responses[(requests.length - 1) % responses.length],
        session_id: String(requests.at(-1)!.session_id),
      },
    })
  })
  const consoleErrors: string[] = []
  page.on('pageerror', (error) => consoleErrors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /A clearer picture/ })).toBeVisible()
  await expect(page.getByText('2026-10-16', { exact: true })).toBeVisible()
  for (const [i, response] of responses.entries()) {
    await page.getByRole('textbox').fill(`Browser regression question ${i + 1}`)
    await page.getByRole('button', { name: 'Send question' }).click()
    await expect(
      page.getByRole('heading', { name: response.visual.title, exact: true }),
    ).toBeVisible()
    await expect(page.getByRole('textbox')).toHaveValue('')
  }
  await expect(page.getByRole('button', { name: /Northeast Block 7, 2026-01:/ })).toBeAttached()
  await page.getByRole('button', { name: /Northeast Block 7, 2026-01:/ }).click()
  await expect(page.locator('.cell-detail')).toContainText('Northeast Block 7')
  expect(requests.every((r) => r.session_id === requests[0].session_id)).toBeTruthy()
  expect(consoleErrors).toEqual([])
  await expect(page.getByText('OpenStreetMap', { exact: true })).toBeAttached()
  await expect(page.getByText(/Map tiles are unavailable/)).toBeAttached()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy()
  await page.getByRole('combobox', { name: 'Demo user' }).selectOption('U-202')
  await expect(page.getByText('Browser regression question 1', { exact: true })).toHaveCount(0)
  await page.getByRole('textbox').fill('New identity')
  await page.getByRole('button', { name: 'Send question' }).click()
  await expect(page.getByRole('textbox')).toHaveValue('')
  expect(requests.at(-1)!.session_id).not.toBe(requests[0].session_id)
  expect(requests.at(-1)!.user_id).toBe('U-202')
  await page.getByRole('button', { name: 'New chat' }).click()
  await expect(page.getByText('New identity', { exact: true })).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Dataset' }).selectOption('test')
  await expect(page.getByText('2025-01-02', { exact: true })).toBeVisible()
  await page.getByRole('textbox').fill('Other dataset')
  await page.getByRole('button', { name: 'Send question' }).click()
  await expect(page.getByRole('textbox')).toHaveValue('')
  expect(requests.at(-1)!.dataset_id).toBe('test')
  expect(requests.at(-1)!.user_id).toBe('U-301')
})

test('uncertain request outcome preserves draft without automatic retries', async ({ page }) => {
  let count = 0
  await page.route('**/health', (route) =>
    route.fulfill({
      json: {
        status: 'ok',
        datasets: [
          {
            dataset_id: 'sample',
            wells: 200,
            users: [{ user_id: 'U-201', name: 'Michael Turner', role: null }],
          },
        ],
      },
    }),
  )
  await page.route('**/ready', (route) =>
    route.fulfill({ status: 503, json: { detail: 'Not ready' } }),
  )
  await page.route('**/chat', (route) => {
    count++
    return route.fulfill({ status: 504, json: { detail: 'Timeout' } })
  })
  await page.goto('/')
  await page.getByRole('textbox').fill('Record this correction')
  await page.getByRole('button', { name: 'Send question' }).click()
  await expect(page.getByRole('alert')).toContainText('Tool writes may already have committed')
  await expect(page.getByRole('textbox')).toHaveValue('Record this correction')
  expect(count).toBe(1)
  await expect(page.getByText(/Data as of/)).toHaveCount(0)
})
