import { EvaluatePage } from './pages/EvaluatePage'

function App() {
  const activePage = window.location.pathname.startsWith('/generate') ? 'generate' : 'evaluate'

  return (
    <main className="h-screen overflow-hidden bg-il-storm-95 text-il-storm-10">
      <div className="mx-auto grid h-full w-full max-w-6xl grid-rows-[64px_minmax(0,1fr)] px-4 sm:px-6 lg:px-8">
        <TopNav activePage={activePage} />
        {activePage === 'generate' ? <GeneratePlaceholder /> : <EvaluatePage />}
      </div>
    </main>
  )
}

function TopNav({ activePage }: { activePage: 'evaluate' | 'generate' }) {
  return (
    <nav className="flex items-center justify-between border-b border-il-storm-20">
      <a href="/evaluate" className="text-lg font-semibold tracking-wide text-il-blue">
        AD Craft
      </a>
      <div className="flex h-full items-center gap-1">
        <NavLink href="/evaluate" isActive={activePage === 'evaluate'}>
          Evaluate
        </NavLink>
        <NavLink href="/generate" isActive={activePage === 'generate'}>
          Generate
        </NavLink>
      </div>
    </nav>
  )
}

function NavLink({
  href,
  isActive,
  children,
}: {
  href: string
  isActive: boolean
  children: string
}) {
  const activeClass = isActive
    ? 'bg-il-blue text-white'
    : 'text-il-blue hover:bg-white hover:text-il-altgeld'
  return (
    <a
      href={href}
      className={`${activeClass} rounded-md px-4 py-2 text-sm font-semibold transition`}
    >
      {children}
    </a>
  )
}

function GeneratePlaceholder() {
  return (
    <section className="flex min-h-0 items-center justify-center py-5">
      <div className="w-full rounded-lg border border-il-storm-20 bg-white p-8 text-center">
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-il-storm-60">
          AD Craft
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-il-blue">Generate</h1>
      </div>
    </section>
  )
}

export default App
