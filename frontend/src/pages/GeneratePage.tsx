import { useState } from 'react'
import { AlertCircle } from 'lucide-react'
import { InputPanel } from '../components/InputPanel'
import { useGenerate, useGenerateTemplateVariant } from '../hooks/useGenerate'
import type {
  CategoryOption,
  GenerateResponse,
  LengthOption,
  StructuredSegment,
  StructuredVariant,
  TemplateCandidate,
} from '../types/generate'

const SEGMENT_STYLE: Record<string, string> = {
  AH: 'bg-blue-100 text-blue-900',
  PP: 'bg-rose-100 text-rose-900',
  AG: 'bg-orange-100 text-orange-900',
  FB: 'bg-emerald-100 text-emerald-900',
  SP: 'bg-violet-100 text-violet-900',
  BA: 'bg-cyan-100 text-cyan-900',
  AU: 'bg-amber-100 text-amber-900',
  UR: 'bg-red-100 text-red-900',
  OF: 'bg-teal-100 text-teal-900',
  CTA: 'bg-indigo-100 text-indigo-900',
}

type ResultKey = string

export function GeneratePage() {
  const generate = useGenerate()
  const generateTemplateVariant = useGenerateTemplateVariant()
  const [category, setCategory] = useState<CategoryOption>('auto')
  const [length, setLength] = useState<LengthOption>('m')
  const [productDesc, setProductDesc] = useState('')
  const [generationPrompt, setGenerationPrompt] = useState('')
  const [resolvedCategory, setResolvedCategory] = useState<string | null>(null)
  const [result, setResult] = useState<GenerateResponse | null>(null)
  const [selectedKey, setSelectedKey] = useState<ResultKey>('direct')
  const [variantMap, setVariantMap] = useState<Record<string, StructuredVariant>>({})
  const [directOutput, setDirectOutput] = useState<string | null>(null)

  const submit = async () => {
    const payload = {
      category,
      length,
      product_desc: productDesc.trim(),
      generation_prompt: generationPrompt.trim() || null,
    }
    const response = await generate.mutateAsync(payload)
    setResult(response)
    setResolvedCategory(response.category)
    setDirectOutput(response.direct_output)
    setSelectedKey(response.structured_variants[0]?.template_id ?? 'direct')
    setVariantMap(
      Object.fromEntries(
        response.structured_variants.map((variant) => [variant.template_id, variant]),
      ),
    )
  }

  const selectTemplate = async (template: TemplateCandidate) => {
    setSelectedKey(template.template_id)
    if (variantMap[template.template_id] !== undefined || resolvedCategory === null) {
      return
    }
    const variant = await generateTemplateVariant.mutateAsync({
      template_id: template.template_id,
      category: resolvedCategory,
      product_desc: productDesc.trim(),
      length,
      generation_prompt: generationPrompt.trim() || null,
    })
    setVariantMap((prev) => ({ ...prev, [template.template_id]: variant }))
  }

  const currentVariant = selectedKey === 'direct' ? null : variantMap[selectedKey]

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] pt-5">
      <header className="rounded-lg border border-il-blue bg-il-blue px-5 py-5 text-white">
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-white/75">Copy Generation</p>
        <h1 className="mt-1 text-3xl font-semibold leading-tight">Generate</h1>
      </header>
      <section className="min-h-0 overflow-y-auto py-5">
        <div className="space-y-5">
          <InputPanel
            category={category}
            productDesc={productDesc}
            generationPrompt={generationPrompt}
            length={length}
            disabled={generate.isPending}
            onCategoryChange={setCategory}
            onProductDescChange={setProductDesc}
            onGenerationPromptChange={setGenerationPrompt}
            onLengthChange={setLength}
            onSubmit={() => {
              void submit()
            }}
          />
          {generate.isError ? (
            <div className="rounded-lg border border-il-altgeld bg-white p-4 text-sm text-il-altgeld">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4" aria-hidden="true" />
                <span>Template search failed. Please try again.</span>
              </div>
            </div>
          ) : null}
          <div className="grid min-h-[420px] gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
            <section className="rounded-lg border border-il-storm-20 bg-white">
              <header className="border-b border-il-storm-20 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-il-storm-60">
                  Selected Category
                </p>
                <p className="mt-1 text-base font-semibold text-il-blue">{resolvedCategory ?? '-'}</p>
              </header>
              <div className="max-h-[560px] overflow-y-auto p-2">
                {(result?.templates ?? []).map((template) => (
                  <button
                    key={template.template_id}
                    type="button"
                    onClick={() => {
                      void selectTemplate(template)
                    }}
                    className={
                      selectedKey === template.template_id
                        ? 'mb-2 w-full rounded-md border border-il-blue bg-il-blue px-3 py-3 text-left text-white'
                        : 'mb-2 w-full rounded-md border border-il-storm-20 bg-white px-3 py-3 text-left text-il-storm-10 hover:border-il-blue'
                    }
                  >
                    <p className="text-sm font-semibold">{template.template_name}</p>
                  </button>
                ))}
                {result !== null ? (
                  <button
                    type="button"
                    onClick={() => setSelectedKey('direct')}
                    className={
                      selectedKey === 'direct'
                        ? 'mb-2 w-full rounded-md border border-il-blue bg-il-blue px-3 py-3 text-left text-white'
                        : 'mb-2 w-full rounded-md border border-il-storm-20 bg-white px-3 py-3 text-left text-il-storm-10 hover:border-il-blue'
                    }
                  >
                    <p className="text-sm font-semibold">No-template generation</p>
                  </button>
                ) : null}
              </div>
            </section>
            <section className="rounded-lg border border-il-storm-20 bg-white">
              <header className="border-b border-il-storm-20 p-4">
                <p className="text-sm font-semibold uppercase tracking-[0.1em] text-il-blue">
                  {selectedKey === 'direct' ? 'Direct Result' : 'Template Result'}
                </p>
                {currentVariant !== null ? (
                  <p className="mt-2 text-sm text-il-storm-60">
                    Sequence: {currentVariant.sequence.join(' -> ')}
                  </p>
                ) : null}
              </header>
              <div className="max-h-[560px] overflow-y-auto p-4">
                {selectedKey === 'direct' ? (
                  <p className="whitespace-pre-wrap leading-8 text-il-storm-10">
                    {directOutput ?? 'Direct result will appear here.'}
                  </p>
                ) : currentVariant !== null ? (
                  <div className="space-y-3">
                    {currentVariant.segments.map((segment: StructuredSegment) => (
                      <div key={`${segment.label}-${segment.text}`} className="space-y-2">
                        <p
                          className={`inline-block rounded px-2 py-1 text-xs font-semibold ${SEGMENT_STYLE[segment.label] ?? 'bg-gray-100 text-gray-900'}`}
                        >
                          {segment.label_full}
                        </p>
                        <p className="whitespace-pre-wrap leading-8 text-il-storm-10">{segment.text}</p>
                      </div>
                    ))}
                  </div>
                ) : generateTemplateVariant.isPending ? (
                  <p className="text-sm text-il-storm-60">Generating selected template copy...</p>
                ) : (
                  <p className="text-sm text-il-storm-60">Select a template to generate result.</p>
                )}
              </div>
            </section>
          </div>
        </div>
      </section>
    </div>
  )
}
