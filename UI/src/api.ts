import { answerSchema, healthSchema } from './contracts'

export class ApiError extends Error {
  status: number
  uncertain: boolean
  constructor(message: string, status = 0, uncertain = false) {
    super(message)
    this.status = status
    this.uncertain = uncertain
  }
}

const errors: Record<number, string> = {
  403: 'This conversation does not match the selected user or dataset. Start a new chat.',
  404: 'The requested dataset is not loaded. Refresh the page to check available datasets.',
  409: 'This conversation already has a request in progress. Wait before sending another question.',
  422: 'The request could not be validated. Check your question and selected context.',
  502: 'The model or its response is unavailable. No verified answer was returned.',
  503: 'The backend or model provider is unavailable. Check the backend and OpenCode service.',
  504: 'The request timed out. The outcome is uncertain.',
}
async function request(path: string, init?: RequestInit) {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiError('Could not reach the backend. Check your connection.', 0, !!init)
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail =
      response.status === 422 && Array.isArray(payload?.detail)
        ? payload.detail
            .map(
              (d: { loc?: string[]; msg?: string }) =>
                `${d.loc?.join('.') || 'Request'}: ${d.msg || 'Invalid value'}`,
            )
            .join('; ')
        : ''
    throw new ApiError(
      `${errors[response.status] || `Backend request failed (HTTP ${response.status}).`}${detail ? ` ${detail}` : ''}`,
      response.status,
      !!init && response.status >= 500,
    )
  }
  try {
    return await response.json()
  } catch {
    throw new ApiError('The backend returned an unreadable response.', response.status, !!init)
  }
}
export async function getHealth() {
  const result = healthSchema.safeParse(await request('/health'))
  if (!result.success)
    throw new ApiError(
      'Dataset metadata is incomplete or invalid. Restart the updated FastAPI backend, then refresh this connection.',
    )
  return result.data
}
export async function getReady() {
  await request('/ready')
}
export async function askQuestion(body: {
  user_id: string
  dataset_id: string
  session_id: string | null
  question: string
}) {
  const json = await request('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const parsed = answerSchema.safeParse(json)
  if (!parsed.success)
    throw new ApiError(
      'The backend returned an invalid answer. No verified answer can be displayed.',
      200,
      true,
    )
  return parsed.data
}
