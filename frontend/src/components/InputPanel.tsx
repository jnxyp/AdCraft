import type { ReactNode } from 'react'
import { Search } from 'lucide-react'
import type { CategoryOption, LengthOption } from '../types/generate'
import { CATEGORIES, getCategoryDisplayName } from '../constants/categories'

const LENGTH_OPTIONS: Array<{ value: LengthOption; label: string; sentenceRange: string }> = [
  { value: 'xs', label: 'XS', sentenceRange: '1-2' },
  { value: 's', label: 'S', sentenceRange: '3' },
  { value: 'm', label: 'M', sentenceRange: '4-5' },
  { value: 'l', label: 'L', sentenceRange: '6-8' },
  { value: 'xl', label: 'XL', sentenceRange: '9-15' },
]

interface InputPanelProps {
  category: CategoryOption
  productDesc: string
  generationPrompt: string
  length: LengthOption
  disabled: boolean
  onCategoryChange: (value: CategoryOption) => void
  onProductDescChange: (value: string) => void
  onGenerationPromptChange: (value: string) => void
  onLengthChange: (value: LengthOption) => void
  onSubmit: () => void
  footerLeft?: ReactNode
}

export function InputPanel(props: InputPanelProps) {
  const rawIndex = LENGTH_OPTIONS.findIndex((option) => option.value === props.length)
  const selectedIndex = rawIndex >= 0 ? rawIndex : 2
  const selected = LENGTH_OPTIONS[selectedIndex] ?? LENGTH_OPTIONS[2]
  const sliderRatio = selectedIndex / (LENGTH_OPTIONS.length - 1)
  const bubbleLeft = `calc(${sliderRatio * 100}% + ${(0.5 - sliderRatio) * 16}px)`

  return (
    <section className="rounded-lg border border-il-storm-20 bg-white p-3">
      <header className="mb-2">
        <p className="text-sm font-semibold uppercase tracking-[0.1em] text-il-blue">Query Configuration</p>
      </header>
      <div className="grid gap-2 lg:grid-cols-2">
        <label className="flex flex-col gap-2 text-xs font-bold text-il-storm-10">
          Product Description (Query String)
          <textarea
            className="h-20 rounded-md border border-il-storm-20 px-3 py-2 leading-6 focus:border-il-blue focus:outline-none focus:ring-2 focus:ring-il-blue/20"
            value={props.productDesc}
            onChange={(event) => props.onProductDescChange(event.target.value)}
            disabled={props.disabled}
          />
          <span className="text-xs font-medium text-il-storm-60">Used for semantic retrieval to find matching templates.</span>
        </label>
        <label className="flex flex-col gap-2 text-xs font-bold text-il-storm-10">
          Additional Guidance (optional)
          <textarea
            className="h-20 rounded-md border border-il-storm-20 px-3 py-2 leading-6 focus:border-il-blue focus:outline-none focus:ring-2 focus:ring-il-blue/20"
            value={props.generationPrompt}
            onChange={(event) => props.onGenerationPromptChange(event.target.value)}
            disabled={props.disabled}
          />
          <span className="text-xs font-medium text-il-storm-60">Controls style, tone, and constraints during generation.</span>
        </label>
      </div>
      <div className="mt-2 grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-2 text-xs font-bold text-il-storm-10">
          Category
          <select
            className="h-11 rounded-md border border-il-storm-20 bg-white px-3 focus:border-il-blue focus:outline-none focus:ring-2 focus:ring-il-blue/20"
            value={props.category}
            onChange={(event) => props.onCategoryChange(event.target.value as CategoryOption)}
            disabled={props.disabled}
          >
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {getCategoryDisplayName(category)}
              </option>
            ))}
          </select>
          <span className="text-xs font-medium text-il-storm-60">Filters template candidates before ranking.</span>
        </label>
        <div className="flex flex-col gap-2 text-xs font-bold text-il-storm-10">
          Length
          <div className="px-1 pt-0.5">
            <div className="relative pt-5">
              <span
                className="absolute top-0 -translate-x-1/2 rounded bg-il-blue px-2 py-0.5 text-xs font-semibold text-white"
                style={{ left: bubbleLeft }}
              >
                {selected.label}
              </span>
              <input
                type="range"
                min={0}
                max={LENGTH_OPTIONS.length - 1}
                step={1}
                value={selectedIndex}
                disabled={props.disabled}
                onChange={(event) => {
                  const nextIndex = Number(event.target.value)
                  const option = LENGTH_OPTIONS[nextIndex]
                  if (option !== undefined) {
                    props.onLengthChange(option.value)
                  }
                }}
                className="h-2 w-full appearance-none rounded-full bg-il-storm-20 accent-[#13294B] [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-il-blue [&::-webkit-slider-thumb]:shadow-sm [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-il-blue"
              />
            </div>
            <div className="mt-1 flex items-center justify-between text-xs font-semibold text-il-storm-60">
              <span>Shorter</span>
              <span>Longer</span>
            </div>
          </div>
          <p className="text-xs font-medium text-il-storm-60">
            Generates about {selected.sentenceRange} sentences. Sets expected structure depth for retrieval and generation.
          </p>
        </div>
      </div>
      <div className="mt-2 flex items-center justify-end gap-2">
        {props.footerLeft ?? null}
        <button
          type="button"
          onClick={props.onSubmit}
          disabled={props.disabled || props.productDesc.trim().length < 8}
          className="inline-flex h-9 items-center gap-1.5 rounded-md border border-il-blue bg-il-blue px-4 text-sm font-semibold text-white transition hover:opacity-90 active:opacity-95 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Search className="h-3.5 w-3.5" aria-hidden="true" />
          {props.disabled ? 'Finding...' : 'Find Template'}
        </button>
      </div>
    </section>
  )
}
