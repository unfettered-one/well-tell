import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ArrowUp,
  ArrowUpRight,
  BarChart3,
  Check,
  ChevronDown,
  CircleHelp,
  Droplets,
  FileText,
  Globe2,
  Layers3,
  LoaderCircle,
  MapPin,
  Plus,
  ShieldCheck,
  Sparkles,
  Thermometer,
  Waves,
} from 'lucide-react'
import { ApiError, askQuestion, getHealth, getReady } from './api'
import type { Answer, Dataset } from './contracts'
import { VisualRenderer } from './components/visuals/VisualRenderer'

type Message =
  { id: string; role: 'user'; text: string } | { id: string; role: 'assistant'; response: Answer }
type Failure = { message: string; uncertain: boolean }
const examples = [
  {
    icon: Waves,
    title: 'Check a well',
    text: 'Is WELL-0001 producing? Show its status card.',
    description: 'Status & inspection evidence',
    tag: 'Status card',
  },
  {
    icon: Thermometer,
    title: 'Trace a trend',
    text: 'Show the recent temperature history for WELL-0001 as a line chart, including the production threshold.',
    description: 'Readings over time',
    tag: 'Line chart',
  },
  {
    icon: BarChart3,
    title: 'Compare downtime',
    text: 'Which wells have the most downtime in this dataset? Show the top 10 as a bar chart.',
    description: 'Find operational outliers',
    tag: 'Bar chart',
  },
  {
    icon: MapPin,
    title: 'Locate spills',
    text: 'Show recorded oil spills on a map with well details and spill volumes.',
    description: 'Explore returned locations',
    tag: 'Map',
  },
  {
    icon: Layers3,
    title: 'See the pattern',
    text: 'Show oil spill counts by area and month as a heatmap.',
    description: 'Area-by-month comparison',
    tag: 'Heatmap',
  },
  {
    icon: FileText,
    title: 'Review compliance',
    text: 'Which spill obligations are breached? Show a table with deadlines, actual values and supporting records.',
    description: 'Deadlines & supporting records',
    tag: 'Table',
  },
]

function BrandMark({ large = false }: { large?: boolean }) {
  return (
    <div className={`brand-mark ${large ? 'large' : ''}`} aria-hidden="true">
      <svg viewBox="0 0 32 32" fill="none">
        <path
          d="M7 11v8a5 5 0 0 0 10 0V9m0 10a4 4 0 0 0 8 0v-8"
          stroke="currentColor"
          strokeWidth="2.6"
          strokeLinecap="round"
        />
        <path d="M7 8v.1M25 8v.1" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
    </div>
  )
}

function AssistantMessage({ response }: { response: Answer }) {
  return (
    <article className="message assistant-message">
      <div className="message-avatar">
        <BrandMark />
      </div>
      <div className="message-content">
        <div className="message-label">
          Well Tell <span>Asset intelligence</span>
        </div>
        <div className="markdown">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            skipHtml
            components={{
              a: ({ children, ...props }) => (
                <a {...props} target="_blank" rel="noopener noreferrer">
                  {children}
                </a>
              ),
              table: ({ children }) => (
                <div className="table-scroll" tabIndex={0}>
                  <table>{children}</table>
                </div>
              ),
            }}
          >
            {response.answer}
          </ReactMarkdown>
        </div>
        <VisualRenderer raw={response.visual} />
        <div className="sources">
          <span className="source-label">
            <ShieldCheck size={13} aria-hidden="true" /> Sources
          </span>
          {response.citations.length ? (
            response.citations.map((citation, i) => (
              <span className="citation" key={`${citation}-${i}`} title={citation}>
                <FileText size={11} aria-hidden="true" />
                {citation}
              </span>
            ))
          ) : (
            <span className="no-sources">No source identifiers returned.</span>
          )}
        </div>
        {response.tool_calls.length > 0 && (
          <details className="tool-summary">
            <summary>{response.tool_calls.length} completed-response tool call(s)</summary>
            <ul>
              {response.tool_calls.map((t, i) => (
                <li key={i}>
                  <code>{t.name}</code>
                  <span>{t.status}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </article>
  )
}

function Conversation({
  dataset,
  userId,
  onPending,
}: {
  dataset: Dataset
  userId: string
  onPending: (busy: boolean) => void
}) {
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)
  const session = useRef<string | null>(null),
    inFlight = useRef(false),
    alive = useRef(true)
  const bottom = useRef<HTMLDivElement>(null),
    textarea = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])
  useEffect(() => {
    if (messages.length || pending || failure)
      bottom.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [messages, pending, failure])

  async function submit(event?: FormEvent) {
    event?.preventDefault()
    const question = draft.trim()
    if (!question || inFlight.current || !userId) return
    inFlight.current = true
    setPending(true)
    onPending(true)
    setFailure(null)
    // Choose a correlation ID before sending, so an uncertain outcome does not
    // lose the conversation identity. This is not an authentication credential.
    session.current ||= `chat-${crypto.randomUUID()}`
    setMessages((previous) => [
      ...previous,
      { id: crypto.randomUUID(), role: 'user', text: question },
    ])
    try {
      const response = await askQuestion({
        user_id: userId,
        dataset_id: dataset.dataset_id,
        session_id: session.current,
        question,
      })
      if (!alive.current) return
      session.current = response.session_id
      setMessages((previous) => [
        ...previous,
        { id: crypto.randomUUID(), role: 'assistant', response },
      ])
      setDraft('')
    } catch (error) {
      if (!alive.current) return
      setFailure({
        message: error instanceof Error ? error.message : 'An unexpected error occurred.',
        uncertain: error instanceof ApiError ? error.uncertain : true,
      })
    } finally {
      inFlight.current = false
      if (alive.current) {
        setPending(false)
        onPending(false)
        setTimeout(() => textarea.current?.focus(), 0)
      }
    }
  }
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void submit()
    }
  }
  const user = dataset.users.find((u) => u.user_id === userId)
  return (
    <>
      <main className="conversation" aria-label="Conversation">
        {messages.length === 0 ? (
          <div className="landing">
            <div className="intro">
              <div className="intro-badge">
                <span /> Your evidence-first copilot
              </div>
              <BrandMark large />
              <h1>
                A clearer picture.
                <br />
                <span>One question away.</span>
              </h1>
              <p>
                Explore your wells, understand the evidence, and find what needs attention. Just
                ask.
              </p>
            </div>
            <div className="suggestions" aria-label="Example questions">
              {examples.map(({ icon: Icon, title, text, description, tag }) => (
                <button
                  className="suggestion"
                  type="button"
                  key={title}
                  onClick={() => {
                    setDraft(text)
                    textarea.current?.focus()
                  }}
                  disabled={!userId}
                >
                  <div className="suggestion-top">
                    <Icon size={19} aria-hidden="true" />
                    <ArrowUpRight size={15} className="suggestion-arrow" aria-hidden="true" />
                  </div>
                  <strong>{title}</strong>
                  <span>{description}</span>
                  <small>{tag}</small>
                </button>
              ))}
            </div>
            <div className="landing-note">
              <ShieldCheck size={14} aria-hidden="true" /> Grounded in your dataset. Backed by
              source records.
            </div>
          </div>
        ) : (
          <div className="thread">
            {messages.map((m) =>
              m.role === 'user' ? (
                <article key={m.id} className="message user-message">
                  <div className="user-bubble">{m.text}</div>
                  <div className="user-avatar" aria-label={user?.name || userId}>
                    {(user?.name || userId)
                      .split(' ')
                      .map((s) => s[0])
                      .slice(0, 2)
                      .join('')}
                  </div>
                </article>
              ) : (
                <AssistantMessage key={m.id} response={m.response} />
              ),
            )}
            {pending && (
              <div className="waiting" role="status">
                <LoaderCircle size={17} className="spin" aria-hidden="true" />
                <div>
                  <strong>Working on your question</strong>
                  <span>
                    Waiting for the backend to finish. No live tool progress is available.
                  </span>
                </div>
              </div>
            )}
            {failure && (
              <div className="request-error" role="alert">
                <strong>We couldn’t complete this answer</strong>
                <p>{failure.message}</p>
                {failure.uncertain && (
                  <p>
                    <strong>Tool writes may already have committed.</strong> Nothing was
                    automatically retried. Verify the outcome before manually sending the question
                    again. Closing this page does not stop server execution.
                  </p>
                )}
                <p>Your question is preserved in the composer.</p>
              </div>
            )}
          </div>
        )}
        <div ref={bottom} />
      </main>
      <footer className="composer-area">
        <div className="composer-wrap">
          <form className={`composer ${pending ? 'is-pending' : ''}`} onSubmit={submit}>
            <label className="sr-only" htmlFor="question">
              Ask about your assets
            </label>
            <textarea
              ref={textarea}
              id="question"
              placeholder={
                messages.length
                  ? 'Ask a follow-up, or request another visual…'
                  : 'Ask anything about your wells, spills, or compliance…'
              }
              value={draft}
              maxLength={20000}
              rows={2}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={keyDown}
              readOnly={pending}
              disabled={!userId}
            />
            <div className="composer-bottom">
              <span>
                <Sparkles size={13} aria-hidden="true" />{' '}
                {pending
                  ? 'Request in progress · no automatic retries'
                  : messages.length
                    ? 'Follow-ups keep this conversation’s context'
                    : 'Ask naturally. Get answers with evidence.'}
              </span>
              <button
                type="submit"
                aria-label="Send question"
                title="Send question (Enter)"
                disabled={!draft.trim() || pending || !userId}
              >
                {pending ? <LoaderCircle size={18} className="spin" /> : <ArrowUp size={19} />}
              </button>
            </div>
          </form>
          <div className="composer-footnote">
            <span>AI can make mistakes. Check the cited records.</span>
            <span>
              Enter to send <span className="key-hint">↵</span>
              <span className="desktop-only"> · Shift + Enter for a new line</span>
            </span>
          </div>
        </div>
      </footer>
    </>
  )
}

export default function App() {
  const [datasets, setDatasets] = useState<Dataset[]>([]),
    [datasetId, setDatasetId] = useState(''),
    [userId, setUserId] = useState('')
  const [generation, setGeneration] = useState(0),
    [pending, setPending] = useState(false)
  const [loading, setLoading] = useState(true),
    [loadError, setLoadError] = useState<string | null>(null)
  const [readiness, setReadiness] = useState<'checking' | 'ready' | 'unavailable'>('checking')
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError(null)
    setReadiness('checking')
    void getHealth()
      .then((health) => {
        if (!active) return
        setDatasets(health.datasets)
        const first = health.datasets[0]
        setDatasetId(first?.dataset_id || '')
        setUserId(first?.users[0]?.user_id || '')
      })
      .catch((error) => {
        if (active)
          setLoadError(error instanceof Error ? error.message : 'Dataset metadata is unavailable.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    void getReady()
      .then(() => {
        if (active) setReadiness('ready')
      })
      .catch(() => {
        if (active) setReadiness('unavailable')
      })
    return () => {
      active = false
    }
  }, [reload])
  const dataset = datasets.find((d) => d.dataset_id === datasetId)
  function changeDataset(id: string) {
    setDatasetId(id)
    setUserId(datasets.find((d) => d.dataset_id === id)?.users[0]?.user_id || '')
    setGeneration((g) => g + 1)
  }
  return (
    <div className="app-shell">
      <header className="app-header">
        <a href="/" className="brand" aria-label="Well Tell home">
          <BrandMark />
          <span>
            well<span className="brand-light">tell</span>
            <span className="brand-dot">.</span>
          </span>
        </a>
        <div className="header-divider" />
        <span className="workspace-name">Asset intelligence</span>
        <div className="header-controls">
          <label className="select-control">
            <Globe2 size={14} aria-hidden="true" />
            <span className="sr-only">Dataset</span>
            <select
              aria-label="Dataset"
              value={datasetId}
              disabled={loading || pending || !datasets.length}
              onChange={(e) => changeDataset(e.target.value)}
            >
              {!datasets.length && <option value="">No datasets</option>}
              {datasets.map((d) => (
                <option key={d.dataset_id} value={d.dataset_id}>
                  {d.dataset_id} dataset
                </option>
              ))}
            </select>
            <ChevronDown size={12} aria-hidden="true" />
          </label>
          <label className="select-control user-select">
            <span className="mini-avatar" aria-hidden="true">
              {(dataset?.users.find((u) => u.user_id === userId)?.name || '?')[0]}
            </span>
            <span className="sr-only">Demo user</span>
            <select
              aria-label="Demo user"
              title="Trusted demo identity, not authentication"
              value={userId}
              disabled={loading || pending || !dataset?.users.length}
              onChange={(e) => {
                setUserId(e.target.value)
                setGeneration((g) => g + 1)
              }}
            >
              {!dataset?.users.length && <option value="">No users</option>}
              {dataset?.users.map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.name || u.user_id} · {u.user_id}
                </option>
              ))}
            </select>
            <ChevronDown size={12} aria-hidden="true" />
          </label>
          <button
            type="button"
            className="new-chat"
            onClick={() => setGeneration((g) => g + 1)}
            disabled={pending || loading}
          >
            <Plus size={16} aria-hidden="true" />
            <span>New chat</span>
          </button>
        </div>
      </header>
      <div className="context-bar">
        <div>
          <span className={`connection-dot ${readiness}`} />
          {readiness === 'ready' ? (
            <>
              <Check size={12} aria-hidden="true" /> Backend connected
            </>
          ) : readiness === 'checking' ? (
            'Checking backend readiness…'
          ) : (
            'Backend dependencies unavailable — check /ready'
          )}
          {dataset && (
            <>
              <span className="context-separator">/</span>
              <span>{dataset.wells.toLocaleString()} wells loaded</span>
              {dataset.as_of && (
                <>
                  <span className="context-separator">/</span>
                  <span>
                    Data as of <strong>{dataset.as_of}</strong>
                  </span>
                </>
              )}
            </>
          )}
        </div>
        <span className="trusted-demo">
          <ShieldCheck size={12} aria-hidden="true" /> Local demo · not authenticated
        </span>
      </div>
      {loading ? (
        <main className="page-state" role="status">
          <LoaderCircle className="spin" />
          <h1>Connecting to your workspace</h1>
          <p>Loading datasets and demo users from the backend.</p>
        </main>
      ) : loadError ? (
        <main className="page-state" role="alert">
          <CircleHelp size={30} />
          <h1>Workspace unavailable</h1>
          <p>{loadError}</p>
          <button className="outline-button" onClick={() => setReload((r) => r + 1)}>
            Refresh connection
          </button>
        </main>
      ) : !dataset || !userId ? (
        <main className="page-state">
          <Droplets size={30} />
          <h1>{dataset ? 'No demo users available' : 'No datasets loaded'}</h1>
          <p>Load a dataset with users through the existing ingestion process, then refresh.</p>
          <button className="outline-button" onClick={() => setReload((r) => r + 1)}>
            Refresh datasets
          </button>
        </main>
      ) : (
        <Conversation
          key={`${datasetId}:${userId}:${generation}`}
          dataset={dataset}
          userId={userId}
          onPending={setPending}
        />
      )}
    </div>
  )
}
