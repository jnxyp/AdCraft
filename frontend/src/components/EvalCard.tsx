import type { EvalAd } from '../types/eval'
import { getCategoryDisplayName } from '../constants/categories'

const PATTERN_FULL_LABEL: Record<string, string> = {
  AH: 'Attention Hook',
  PP: 'Pain Point',
  AG: 'Agitation',
  FB: 'Feature-Benefit',
  SP: 'Social Proof',
  BA: 'Before-After',
  AU: 'Authority',
  UR: 'Urgency',
  OF: 'Offer',
  CTA: 'Call To Action',
}

interface EvalCardProps {
  ad: EvalAd
  label: 'A' | 'B'
  category: string | null
  showDetails: boolean
}

export function EvalCard({ ad, label, category, showDetails }: EvalCardProps) {
  return (
    <article className="flex min-h-0 flex-col rounded-lg border border-il-storm-20 bg-white">
      <header className="shrink-0 border-b border-il-storm-20 px-5 py-4">
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-il-blue">
          AD Sample {label}
        </h2>
        <div className="mt-2 flex flex-wrap gap-2">
          <span className="rounded border border-il-orange bg-orange-50 px-2 py-0.5 text-xs font-semibold text-il-altgeld">
            {category ? getCategoryDisplayName(category) : 'Loading'}
          </span>
          <span className="rounded border border-il-blue bg-blue-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-il-blue">
            Length: {formatLengthBucket(ad.length_bucket)} · {ad.seq_len}
          </span>
          {showDetails ? (
            <>
              <span className="rounded border border-il-storm-20 bg-white px-2 py-0.5 text-xs font-semibold text-il-storm-60">
                AD ID: {ad.ad_id}
              </span>
              <span
                className="rounded border border-il-storm-20 bg-white px-2 py-0.5 text-xs font-semibold text-il-storm-60"
                title="SC = Semantic Cluster ID from the clustering pipeline."
              >
                SC: {ad.cluster_id && ad.cluster_id.length > 0 ? ad.cluster_id : 'NA'}
              </span>
            </>
          ) : null}
        </div>
        {showDetails ? (
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs font-medium text-il-storm-60">
            {ad.sequence.map((pattern, index) => (
              <div key={`${pattern}-${index}`} className="flex items-center gap-1.5">
                <span
                  className="rounded border border-il-storm-20 bg-il-storm-95 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-il-storm-60"
                  title={PATTERN_FULL_LABEL[pattern] ?? pattern}
                >
                  {pattern}
                </span>
                {index < ad.sequence.length - 1 ? (
                  <span className="text-il-storm-40" aria-hidden="true">
                    →
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
        <p className="whitespace-pre-wrap text-left text-[17px] leading-8 text-il-storm-10">
          {ad.body}
        </p>
      </div>
    </article>
  )
}

function formatLengthBucket(lengthBucket: EvalAd['length_bucket']) {
  return lengthBucket.toUpperCase()
}
