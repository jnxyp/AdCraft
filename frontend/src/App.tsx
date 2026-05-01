import { useEffect, useState } from 'react'
import { EvaluatePage } from './pages/EvaluatePage'
import { GeneratePage } from './pages/GeneratePage'

function App() {
  const [activePage, setActivePage] = useState<'evaluate' | 'generate'>(() =>
    window.location.pathname.startsWith('/generate') ? 'generate' : 'evaluate',
  )

  useEffect(() => {
    const onPopState = () => {
      setActivePage(window.location.pathname.startsWith('/generate') ? 'generate' : 'evaluate')
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

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
          <TopNav activePage={activePage} onNavigate={navigate} />
        </div>
        <section className="min-h-0">
          <div className={activePage === 'evaluate' ? 'h-full' : 'hidden'}>
            <EvaluatePage />
          </div>
          <div className={activePage === 'generate' ? 'h-full' : 'hidden'}>
            <GeneratePage />
          </div>
        </section>
      </div>
    </main>
  )
}

function TopNav({
  activePage,
  onNavigate,
}: {
  activePage: 'evaluate' | 'generate'
  onNavigate: (nextPage: 'evaluate' | 'generate') => void
}) {
  return (
    <nav className="flex h-full select-none items-center justify-between rounded-lg border border-il-storm-20 bg-white px-4 shadow-sm">
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
      <div className="inline-flex items-center rounded-full border border-il-storm-20 bg-il-storm-95 p-1">
        <NavLink href="/evaluate" isActive={activePage === 'evaluate'} onClick={() => onNavigate('evaluate')}>
          Evaluate
        </NavLink>
        <NavLink href="/generate" isActive={activePage === 'generate'} onClick={() => onNavigate('generate')}>
          Generate
        </NavLink>
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
