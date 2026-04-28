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

const LENGTH_OPTIONS: Array<{ value: LengthOption; label: string }> = [
  { value: 'xs', label: 'XS' },
  { value: 's', label: 'S' },
  { value: 'm', label: 'M' },
  { value: 'l', label: 'L' },
  { value: 'xl', label: 'XL' },
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
  return (
    <section className="rounded-lg border border-il-storm-20 bg-white p-5">
      <label className="mt-4 flex flex-col gap-2 text-sm font-medium text-il-storm-10">
        Product Description
        <textarea
          className="min-h-28 rounded-md border border-il-storm-20 px-3 py-2 leading-7"
          value={props.productDesc}
          onChange={(event) => props.onProductDescChange(event.target.value)}
          disabled={props.disabled}
        />
      </label>
      <label className="mt-4 flex flex-col gap-2 text-sm font-medium text-il-storm-10">
        Additional Guidance (optional)
        <textarea
          className="min-h-24 rounded-md border border-il-storm-20 px-3 py-2 leading-7"
          value={props.generationPrompt}
          onChange={(event) => props.onGenerationPromptChange(event.target.value)}
          disabled={props.disabled}
        />
      </label>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
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
          <div className="grid grid-cols-5 gap-2">
            {LENGTH_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                disabled={props.disabled}
                onClick={() => props.onLengthChange(option.value)}
                className={
                  props.length === option.value
                    ? 'h-11 rounded-md border border-il-blue bg-il-blue text-sm font-semibold text-white'
                    : 'h-11 rounded-md border border-il-storm-20 bg-white text-sm font-semibold text-il-storm-10 hover:border-il-blue'
                }
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <button
        type="button"
        onClick={props.onSubmit}
        disabled={props.disabled || props.productDesc.trim().length < 8}
        className="mt-5 h-12 rounded-md bg-il-blue px-5 text-sm font-semibold text-white transition hover:bg-il-orange hover:text-il-blue disabled:cursor-not-allowed disabled:opacity-60"
      >
        {props.disabled ? 'Finding...' : 'Find Template'}
      </button>
    </section>
  )
}
