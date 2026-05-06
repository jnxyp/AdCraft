import { useEffect, useState } from 'react'
import { EvaluatePage } from './pages/EvaluatePage'
import { GeneratePage } from './pages/GeneratePage'

const SESSION_ID_KEY = 'adcraft_session_id'
const EXPLAIN_VISIBILITY_KEY_PREFIX = 'adcraft_explain_visibility_'
const GIT_COMMIT = import.meta.env.VITE_GIT_COMMIT?.trim() || 'unknown'
const DISPLAY_GIT_COMMIT = GIT_COMMIT === 'unknown' ? 'Build.unknown' : `Build.${GIT_COMMIT.slice(0, 8)}`

function getOrCreateSessionId(): string {
  const existing = window.localStorage.getItem(SESSION_ID_KEY)
  if (existing && existing.trim().length > 0) {
    return existing
  }
  const created = crypto.randomUUID()
  window.localStorage.setItem(SESSION_ID_KEY, created)
  return created
}

function App() {
  const [sessionId] = useState<string>(() => getOrCreateSessionId())
  const explainVisibilityKey = `${EXPLAIN_VISIBILITY_KEY_PREFIX}${sessionId}`
  const [activePage, setActivePage] = useState<'evaluate' | 'generate'>(() =>
    window.location.pathname.startsWith('/generate') ? 'generate' : 'evaluate',
  )
  const [showExplainability, setShowExplainability] = useState<boolean>(() => {
    const raw = window.localStorage.getItem(explainVisibilityKey)
    if (raw === null) {
      return true
    }
    return raw === '1'
  })

  useEffect(() => {
    window.localStorage.setItem(explainVisibilityKey, showExplainability ? '1' : '0')
  }, [explainVisibilityKey, showExplainability])

  useEffect(() => {
    const onPopState = () => {
      setActivePage(window.location.pathname.startsWith('/generate') ? 'generate' : 'evaluate')
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    document.title = activePage === 'generate' ? 'AdCraft · Generate' : 'AdCraft · Evaluate'
  }, [activePage])

  const navigate = (nextPage: 'evaluate' | 'generate') => {
    if (nextPage === activePage) {
      return
    }
    const nextPath = nextPage === 'generate' ? '/generate' : '/evaluate'
    window.history.pushState({}, '', nextPath)
    setActivePage(nextPage)
  }

  return (
    <main className="h-screen overflow-hidden bg-il-storm-95 p-[5px] text-il-storm-10">
      <div className="grid h-full w-full grid-rows-[56px_minmax(0,1fr)] gap-[10px]">
        <div>
          <TopNav
            activePage={activePage}
            onNavigate={navigate}
            showExplainability={showExplainability}
            onToggleExplainability={() => setShowExplainability((prev) => !prev)}
          />
        </div>
        <section className="min-h-0">
          <div className={activePage === 'evaluate' ? 'h-full' : 'hidden'}>
            <EvaluatePage showDetails={showExplainability} />
          </div>
          <div className={activePage === 'generate' ? 'h-full' : 'hidden'}>
            <GeneratePage showExplainability={showExplainability} />
          </div>
        </section>
      </div>
    </main>
  )
}

function TopNav({
  activePage,
  onNavigate,
  showExplainability,
  onToggleExplainability,
}: {
  activePage: 'evaluate' | 'generate'
  onNavigate: (nextPage: 'evaluate' | 'generate') => void
  showExplainability: boolean
  onToggleExplainability: () => void
}) {
  return (
    <nav className="flex h-full select-none items-center justify-between rounded-lg border border-il-storm-20 bg-white px-4 shadow-sm">
      <div className="inline-flex min-w-0 items-baseline gap-3">
        <a
          href="/evaluate"
          onClick={(event) => {
            event.preventDefault()
            onNavigate('evaluate')
          }}
          className="inline-flex items-center leading-none tracking-wide"
          style={{ fontFamily: '"Orbitron", sans-serif', fontSize: '2.25rem', fontWeight: 700 }}
        >
          <span className="text-il-blue">Ad</span>
          <span className="text-il-altgeld">Craft</span>
        </a>
        <span
          className="hidden font-mono text-xs font-semibold text-il-storm-60 sm:inline-flex"
          title={`Git commit: ${GIT_COMMIT}`}
        >
          {DISPLAY_GIT_COMMIT}
        </span>
      </div>
      <div className="inline-flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleExplainability}
          className={
            showExplainability
              ? 'rounded-full border border-il-blue bg-il-blue px-4 py-1.5 text-sm font-semibold text-white'
              : 'rounded-full border border-il-storm-20 bg-white px-4 py-1.5 text-sm font-semibold text-il-storm-60'
          }
          title="Show or hide detailed scores and evaluation metadata"
        >
          Show Details
        </button>
        <div className="inline-flex items-center rounded-full border border-il-storm-20 bg-il-storm-95 p-1">
        <NavLink href="/evaluate" isActive={activePage === 'evaluate'} onClick={() => onNavigate('evaluate')}>
          Evaluate
        </NavLink>
        <NavLink href="/generate" isActive={activePage === 'generate'} onClick={() => onNavigate('generate')}>
          Generate
        </NavLink>
        </div>
      </div>
    </nav>
  )
}

function NavLink({
  href,
  isActive,
  onClick,
  children,
}: {
  href: string
  isActive: boolean
  onClick: () => void
  children: string
}) {
  const activeClass = isActive
    ? 'bg-il-blue text-white shadow-sm'
    : 'text-il-blue hover:bg-white active:bg-white'
  return (
    <a
      href={href}
      onClick={(event) => {
        event.preventDefault()
        onClick()
      }}
      className={`${activeClass} rounded-full px-4 py-1.5 text-sm font-semibold transition`}
    >
      {children}
    </a>
  )
}

export default App
