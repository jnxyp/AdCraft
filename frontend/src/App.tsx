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
    <main className="h-screen overflow-hidden bg-il-storm-95 text-il-storm-10">
      <div className="grid h-full w-full grid-rows-[64px_minmax(0,1fr)] px-4 sm:px-6 lg:px-8">
        <TopNav activePage={activePage} onNavigate={navigate} />
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
    <nav className="flex items-center justify-between border-b border-il-storm-20">
      <button
        type="button"
        onClick={() => onNavigate('evaluate')}
        className="text-lg font-semibold tracking-wide text-il-blue"
      >
        AD Craft
      </button>
      <div className="flex h-full items-center gap-1">
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
    ? 'border border-il-blue bg-il-blue text-white'
    : 'border border-il-blue bg-white text-il-blue hover:bg-il-blue hover:text-white active:bg-il-blue active:text-white'
  return (
    <a
      href={href}
      onClick={(event) => {
        event.preventDefault()
        onClick()
      }}
      className={`${activeClass} rounded-md px-4 py-2 text-sm font-semibold transition`}
    >
      {children}
    </a>
  )
}

export default App
