import type { CategoryOption, LengthOption } from '../types/generate'

const CATEGORIES = [
  'auto',
  'tech',
  'beauty',
  'health',
  'ecommerce',
  'finance',
  'home',
  'travel',
  'food',
  'education',
  'entertainment',
  'automotive',
]

const LENGTH_OPTIONS: Array<{ value: LengthOption; label: string; sentenceRange: string }> = [
  { value: 'xs', label: 'XS', sentenceRange: '1-2' },
  { value: 's', label: 'S', sentenceRange: '3-3' },
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
}

export function InputPanel(props: InputPanelProps) {
  const selectedIndex = LENGTH_OPTIONS.findIndex((option) => option.value === props.length)
  const selected = LENGTH_OPTIONS[selectedIndex] ?? LENGTH_OPTIONS[2]
  const sliderPercent = `${(selectedIndex / (LENGTH_OPTIONS.length - 1)) * 100}%`

  return (
    <section className="rounded-lg border border-il-storm-20 bg-white p-4">
      <div className="grid gap-3 lg:grid-cols-2">
        <label className="flex flex-col gap-2 text-sm font-medium text-il-storm-10">
          Product Description
          <textarea
            className="h-28 rounded-md border border-il-storm-20 px-3 py-2 leading-6"
            value={props.productDesc}
            onChange={(event) => props.onProductDescChange(event.target.value)}
            disabled={props.disabled}
          />
        </label>
        <label className="flex flex-col gap-2 text-sm font-medium text-il-storm-10">
          Additional Guidance (optional)
          <textarea
            className="h-28 rounded-md border border-il-storm-20 px-3 py-2 leading-6"
            value={props.generationPrompt}
            onChange={(event) => props.onGenerationPromptChange(event.target.value)}
            disabled={props.disabled}
          />
        </label>
      </div>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <label className="flex flex-col gap-2 text-sm font-medium text-il-storm-10">
          Category
          <select
            className="h-11 rounded-md border border-il-storm-20 bg-white px-3"
            value={props.category}
            onChange={(event) => props.onCategoryChange(event.target.value as CategoryOption)}
            disabled={props.disabled}
          >
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-col gap-2 text-sm font-medium text-il-storm-10">
          Length
          <div className="rounded-md border border-il-storm-20 px-3 py-3">
            <div className="relative mb-2 h-5">
              <span
                className="absolute -translate-x-1/2 rounded bg-il-blue px-2 py-0.5 text-xs font-semibold text-white"
                style={{ left: sliderPercent }}
              >
                {selected.label}
              </span>
            </div>
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
              className="w-full accent-[#13294B]"
            />
            <div className="mt-2 flex items-center justify-between text-xs font-semibold text-il-storm-60">
              <span>Shorter</span>
              <span>Longer</span>
            </div>
          </div>
          <p className="text-xs text-il-storm-60">
            Generates about {selected.sentenceRange} sentences.
          </p>
        </div>
      </div>
      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={props.onSubmit}
          disabled={props.disabled || props.productDesc.trim().length < 8}
          className="h-11 rounded-md bg-il-blue px-5 text-sm font-semibold text-white transition hover:bg-il-orange hover:text-il-blue disabled:cursor-not-allowed disabled:opacity-60"
        >
          {props.disabled ? 'Finding...' : 'Find Template'}
        </button>
      </div>
    </section>
  )
}
