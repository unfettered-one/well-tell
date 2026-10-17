import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi, it, expect } from 'vitest'
import App from '../App'
import captures from './fixtures/captured-responses.json'

const datasets = [
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
    wells: 3,
    as_of: '2025-01-02',
    users: [{ user_id: 'U-999', name: 'Test User', role: 'operator' }],
  },
]
function stubFetch(chat: (body: Record<string, unknown>) => Promise<Response>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (input === '/health') return Response.json({ status: 'ok', datasets })
    if (input === '/ready') return Response.json({ status: 'ready' })
    return chat(JSON.parse(String(init?.body)))
  })
}
async function send(question: string) {
  fireEvent.change(await screen.findByRole('textbox', { name: 'Ask about your assets' }), {
    target: { value: question },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send question' }))
}
it('reuses session, clears user/dataset context and starts fresh on new chat', async () => {
  const requests: Record<string, unknown>[] = []
  stubFetch(async (body) => {
    requests.push(body)
    return Response.json({ ...captures.responses.status_card, session_id: String(body.session_id) })
  })
  render(<App />)
  await send('First real question')
  await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue(''))
  await send('Follow-up')
  await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue(''))
  expect(requests[1].session_id).toBe(requests[0].session_id)
  expect(requests[1].user_id).toBe('U-201')
  fireEvent.change(screen.getByRole('combobox', { name: 'Demo user' }), {
    target: { value: 'U-202' },
  })
  expect(screen.queryByText('First real question')).not.toBeInTheDocument()
  await send('Second user question')
  await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue(''))
  expect(requests[2].session_id).not.toBe(requests[0].session_id)
  expect(requests[2].user_id).toBe('U-202')
  fireEvent.change(screen.getByRole('combobox', { name: 'Dataset' }), { target: { value: 'test' } })
  expect(screen.queryByText('Second user question')).not.toBeInTheDocument()
  expect(screen.getByText('2025-01-02')).toBeInTheDocument()
  await send('Other dataset')
  await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue(''))
  expect(requests[3]).toMatchObject({ dataset_id: 'test', user_id: 'U-999' })
  expect(requests[3].session_id).not.toBe(requests[2].session_id)
  fireEvent.click(screen.getByRole('button', { name: 'New chat' }))
  expect(screen.queryByText('Other dataset')).not.toBeInTheDocument()
  await send('Fresh conversation')
  await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue(''))
  expect(requests[4].session_id).not.toBe(requests[3].session_id)
})
it('prevents duplicate submission and context switching while a turn is pending', async () => {
  let resolve!: (r: Response) => void
  const chat = vi.fn(
    () =>
      new Promise<Response>((r) => {
        resolve = r
      }),
  )
  stubFetch(chat)
  render(<App />)
  await send('Slow question')
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter', code: 'Enter' })
  expect(chat).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Send question' })).toBeDisabled()
  expect(screen.getByRole('combobox', { name: 'Demo user' })).toBeDisabled()
  expect(screen.getByRole('combobox', { name: 'Dataset' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'New chat' })).toBeDisabled()
  expect(screen.getByText(/No live tool progress/)).toBeInTheDocument()
  resolve(Response.json(captures.responses.table))
  await waitFor(() => expect(screen.getByRole('button', { name: 'New chat' })).toBeEnabled())
})
it.each([403, 404, 409, 422, 502, 503, 504])(
  'preserves the draft and never retries HTTP %i',
  async (status) => {
    const chat = vi.fn(async () => Response.json({ detail: 'Failure' }, { status }))
    stubFetch(chat)
    render(<App />)
    await send('Preserve my question')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveValue('Preserve my question')
    expect(chat).toHaveBeenCalledTimes(1)
    if (status >= 500)
      expect(screen.getByText(/Tool writes may already have committed/)).toBeInTheDocument()
  },
)
it('keeps answers and exact citation chips when a visual is invalid, and disables raw HTML', async () => {
  stubFetch(async () =>
    Response.json({
      session_id: 'chat-safe',
      answer: '**Verified answer** <script>alert(1)</script>',
      citations: ['INS-0001-0203', 'fleet/well-types/T200.md'],
      visual: { type: 'unknown', data: [{ well: 'A' }] },
      tool_calls: [],
    }),
  )
  const { container } = render(<App />)
  await send('Show malformed visual')
  expect(await screen.findByText('Verified answer')).toBeInTheDocument()
  expect(screen.getByText('INS-0001-0203')).toBeInTheDocument()
  expect(screen.getByText('fleet/well-types/T200.md')).toBeInTheDocument()
  expect(screen.getByText(/Visual unavailable/)).toBeInTheDocument()
  expect(container.querySelector('script')).toBeNull()
})
it('handles an uncertain network failure without replaying a turn', async () => {
  const chat = vi.fn(async () => {
    throw new TypeError('Network failed')
  })
  stubFetch(chat)
  render(<App />)
  await send('Network outcome unknown')
  expect(await screen.findByRole('alert')).toHaveTextContent('Nothing was automatically retried')
  expect(screen.getByRole('textbox')).toHaveValue('Network outcome unknown')
  expect(chat).toHaveBeenCalledTimes(1)
})
