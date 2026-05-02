import type { EvalAd } from '../types/eval'
import { getCategoryDisplayName } from '../constants/categories'

interface EvalCardProps {
  ad: EvalAd
  label: 'A' | 'B'
  category: string | null
}

export function EvalCard({ ad, label, category }: EvalCardProps) {
  return (
    <article className="flex min-h-0 flex-col rounded-lg border border-il-storm-20 bg-white">
      <header className="shrink-0 border-b border-il-storm-20 px-5 py-4">
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-il-blue">
          AD Sample {label}
        </h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="rounded border border-il-storm-20 px-2 py-1 text-xs font-medium text-il-storm-60">
            {category ? getCategoryDisplayName(category) : 'Loading'}
          </span>
          <span className="rounded border border-il-storm-20 px-2 py-1 text-xs font-medium text-il-storm-60">
            {ad.ad_id}
          </span>
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
        <p className="whitespace-pre-wrap text-left text-[17px] leading-8 text-il-storm-10">
          {ad.body}
        </p>
      </div>
    </article>
  )
}
