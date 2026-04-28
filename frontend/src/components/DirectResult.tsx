interface DirectResultProps {
  output: string | null
}

export function DirectResult({ output }: DirectResultProps) {
  return (
    <section className="rounded-lg border border-il-storm-20 bg-white">
      <header className="border-b border-il-storm-20 p-4">
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-il-blue">Direct</h2>
      </header>
      <div className="p-4">
        <p className="whitespace-pre-wrap leading-8 text-il-storm-10">
          {output ?? 'Direct output will appear here.'}
        </p>
      </div>
    </section>
  )
}
