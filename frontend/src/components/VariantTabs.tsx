import type { StructuredVariant } from '../types/generate'

interface VariantTabsProps {
  variants: StructuredVariant[]
  selectedIndex: number
  onSelect: (index: number) => void
}

export function VariantTabs({ variants, selectedIndex, onSelect }: VariantTabsProps) {
  if (variants.length === 0) {
    return (
      <section className="rounded-lg border border-il-storm-20 bg-white p-6">
        <p className="text-sm text-il-storm-60">Structured variants will appear here.</p>
      </section>
    )
  }

  const current = variants[selectedIndex] ?? variants[0]
  return (
    <section className="rounded-lg border border-il-storm-20 bg-white">
      <header className="border-b border-il-storm-20 p-4">
        <div className="flex flex-wrap gap-2">
          {variants.map((variant, index) => (
            <button
              key={variant.template_id}
              type="button"
              onClick={() => onSelect(index)}
              className={
                index === selectedIndex
                  ? 'rounded-md border border-il-blue bg-il-blue px-3 py-2 text-xs font-semibold text-white'
                  : 'rounded-md border border-il-blue bg-white px-3 py-2 text-xs font-semibold text-il-blue hover:bg-il-blue hover:text-white active:bg-il-blue active:text-white'
              }
            >
              Variant {index + 1}
            </button>
          ))}
        </div>
        <p className="mt-3 text-sm font-semibold text-il-blue">{current.template_name}</p>
      </header>
      <div className="p-4">
        <p className="whitespace-pre-wrap leading-8 text-il-storm-10">{current.output}</p>
      </div>
    </section>
  )
}
