import { useEffect, useState } from 'react'
import { AlertCircle, Check, LoaderCircle } from 'lucide-react'
import { InputPanel } from '../components/InputPanel'
import { getCategoryDisplayName } from '../constants/categories'
import {
  useFindTemplates,
  useGenerateDirect,
  useGenerateTemplateVariant,
} from '../hooks/useGenerate'
import type {
  CategoryOption,
  FindTemplatesResponse,
  LengthOption,
  StructuredSegment,
  StructuredVariant,
  TemplateCandidate,
} from '../types/generate'

const SEGMENT_STYLE: Record<string, string> = {
  AH: 'bg-blue-100 text-blue-900 border-blue-200',
  PP: 'bg-rose-100 text-rose-900 border-rose-200',
  AG: 'bg-orange-100 text-orange-900 border-orange-200',
  FB: 'bg-emerald-100 text-emerald-900 border-emerald-200',
  SP: 'bg-violet-100 text-violet-900 border-violet-200',
  BA: 'bg-cyan-100 text-cyan-900 border-cyan-200',
  AU: 'bg-amber-100 text-amber-900 border-amber-200',
  UR: 'bg-red-100 text-red-900 border-red-200',
  OF: 'bg-teal-100 text-teal-900 border-teal-200',
  CTA: 'bg-indigo-100 text-indigo-900 border-indigo-200',
}

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

type ResultKey = string | null
type GenerationStatus = 'idle' | 'loading' | 'done' | 'error'

export function GeneratePage() {
  const findTemplates = useFindTemplates()
  const generateDirect = useGenerateDirect()
  const generateTemplateVariant = useGenerateTemplateVariant()
  const [category, setCategory] = useState<CategoryOption>('auto')
  const [length, setLength] = useState<LengthOption>('m')
  const [productDesc, setProductDesc] = useState('')
  const [generationPrompt, setGenerationPrompt] = useState('')
  const [resolvedCategory, setResolvedCategory] = useState<string | null>(null)
  const [result, setResult] = useState<FindTemplatesResponse | null>(null)
  const [selectedKey, setSelectedKey] = useState<ResultKey>(null)
  const [variantMap, setVariantMap] = useState<Record<string, StructuredVariant>>({})
  const [statusMap, setStatusMap] = useState<Record<string, GenerationStatus>>({})
  const [directOutput, setDirectOutput] = useState<string | null>(null)
  const [hoveredSegmentIndex, setHoveredSegmentIndex] = useState<number | null>(null)

  const submit = async () => {
    const payload = {
      category,
      length,
      product_desc: productDesc.trim(),
      generation_prompt: generationPrompt.trim() || null,
    }
    const response = await findTemplates.mutateAsync(payload)
    setResult(response)
    setResolvedCategory(response.category)
    setDirectOutput(null)
    setVariantMap({})
    setSelectedKey(response.templates[0]?.template_id ?? null)

    const topThreeIds = response.templates.slice(0, 3).map((template) => template.template_id)
    const nextStatus: Record<string, GenerationStatus> = { direct: 'loading' }
    for (const templateId of topThreeIds) {
      nextStatus[templateId] = 'loading'
    }
    setStatusMap(nextStatus)

    for (const template of response.templates.slice(0, 3)) {
      void generateTemplateFor(
        template,
        response.category,
        response.product_desc,
        response.length,
        payload.generation_prompt,
      )
    }
    void generateDirectOutput(
      response.category as CategoryOption,
      response.product_desc,
      response.length,
      payload.generation_prompt,
    )
  }

  const generateTemplateFor = async (
    template: TemplateCandidate,
    categoryForGeneration: string,
    productDescForGeneration: string,
    lengthForGeneration: LengthOption,
    promptForGeneration: string | null,
  ) => {
    setStatusMap((prev) => ({ ...prev, [template.template_id]: 'loading' }))
    try {
      const variant = await generateTemplateVariant.mutateAsync({
        template_id: template.template_id,
        category: categoryForGeneration,
        product_desc: productDescForGeneration,
        length: lengthForGeneration,
        generation_prompt: promptForGeneration,
      })
      setVariantMap((prev) => ({ ...prev, [template.template_id]: variant }))
      setStatusMap((prev) => ({ ...prev, [template.template_id]: 'done' }))
    } catch {
      setStatusMap((prev) => ({ ...prev, [template.template_id]: 'error' }))
    }
  }

  const generateDirectOutput = async (
    selectedCategory: CategoryOption,
    selectedProductDesc: string,
    selectedLength: LengthOption,
    selectedPrompt: string | null,
  ) => {
    setStatusMap((prev) => ({ ...prev, direct: 'loading' }))
    try {
      const response = await generateDirect.mutateAsync({
        category: selectedCategory,
        product_desc: selectedProductDesc,
        length: selectedLength,
        generation_prompt: selectedPrompt,
      })
      setDirectOutput(response.output)
      setStatusMap((prev) => ({ ...prev, direct: 'done' }))
    } catch {
      setStatusMap((prev) => ({ ...prev, direct: 'error' }))
    }
  }

  const selectTemplate = async (template: TemplateCandidate) => {
    setSelectedKey(template.template_id)
    if (variantMap[template.template_id] !== undefined || result === null || resolvedCategory === null) {
      return
    }
    await generateTemplateFor(
      template,
      resolvedCategory,
      result.product_desc,
      result.length,
      generationPrompt.trim() || null,
    )
  }

  const currentVariant: StructuredVariant | null =
    selectedKey === null || selectedKey === 'direct' ? null : (variantMap[selectedKey] ?? null)
  const selectedTemplate = selectedKey === null || selectedKey === 'direct'
    ? null
    : (result?.templates.find((template) => template.template_id === selectedKey) ?? null)
  const currentStatus = statusMap[selectedKey] ?? 'idle'

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] pt-5">
      <header className="rounded-lg border border-il-blue bg-il-blue px-5 py-5 text-white">
        <h1 className="text-4xl font-bold tracking-[0.04em]">Copy Generation</h1>
      </header>
      <section className="min-h-0 overflow-y-auto py-5">
        <div className="space-y-5">
          <InputPanel
            category={category}
            productDesc={productDesc}
            generationPrompt={generationPrompt}
            length={length}
            disabled={findTemplates.isPending}
            onCategoryChange={setCategory}
            onProductDescChange={setProductDesc}
            onGenerationPromptChange={setGenerationPrompt}
            onLengthChange={setLength}
            onSubmit={() => {
              void submit()
            }}
          />
          {findTemplates.isError ? (
            <div className="rounded-lg border border-il-altgeld bg-white p-4 text-sm text-il-altgeld">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4" aria-hidden="true" />
                <span>Template search failed. Please try again.</span>
              </div>
            </div>
          ) : null}
          <section className="grid min-h-[420px] overflow-hidden rounded-lg border border-il-storm-20 bg-white lg:grid-cols-[340px_minmax(0,1fr)]">
            <aside className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] border-b border-il-storm-20 lg:border-b-0 lg:border-r lg:border-r-il-storm-20">
              <header className="border-b border-il-storm-20 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-il-storm-60">
                  Selected Category
                </p>
                <p className="mt-1 text-base font-semibold text-il-blue">
                  {resolvedCategory !== null ? getCategoryDisplayName(resolvedCategory) : '-'}
                </p>
              </header>
              <div className="min-h-0 overflow-y-auto p-2">
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
                        : 'mb-2 w-full rounded-md border border-il-blue bg-white px-3 py-3 text-left text-il-blue hover:bg-il-blue hover:text-white active:bg-il-blue active:text-white'
                    }
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold">{template.template_name}</p>
                      {(statusMap[template.template_id] ?? 'idle') === 'loading' ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                      ) : (statusMap[template.template_id] ?? 'idle') === 'done' ? (
                        <Check className="h-4 w-4" aria-hidden="true" />
                      ) : null}
                    </div>
                  </button>
                ))}
                {result !== null ? (
                  <button
                    type="button"
                    onClick={() => setSelectedKey('direct')}
                    className={
                      selectedKey === 'direct'
                        ? 'mb-2 w-full rounded-md border border-il-blue bg-il-blue px-3 py-3 text-left text-white'
                        : (statusMap.direct ?? 'idle') === 'done'
                          ? 'mb-2 w-full rounded-md border-2 border-il-orange bg-white px-3 py-3 text-left text-il-orange hover:bg-il-orange hover:text-white active:bg-il-orange active:text-white'
                          : 'mb-2 w-full rounded-md border border-il-blue bg-white px-3 py-3 text-left text-il-blue hover:bg-il-blue hover:text-white active:bg-il-blue active:text-white'
                    }
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold">No-template generation</p>
                      {(statusMap.direct ?? 'idle') === 'loading' ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                      ) : (statusMap.direct ?? 'idle') === 'done' ? (
                        <Check className="h-4 w-4" aria-hidden="true" />
                      ) : null}
                    </div>
                  </button>
                ) : null}
              </div>
            </aside>
            <section className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)]">
              <header className="border-b border-il-storm-20 p-4">
                <p className="text-sm font-semibold uppercase tracking-[0.1em] text-il-blue">
                  {selectedKey === null ? 'No Result Selected' : selectedKey === 'direct' ? 'Direct Result' : 'Template Result'}
                </p>
                {selectedTemplate ? (
                  <div className="mt-3 flex flex-wrap items-center gap-0">
                    {selectedTemplate.sequence.map((code, index) => {
                      const isHovered = hoveredSegmentIndex === index
                      const tagStyle = SEGMENT_STYLE[code] ?? 'bg-gray-100 text-gray-900 border-gray-200'
                      const label = currentVariant?.segments[index]?.label_full ?? PATTERN_FULL_LABEL[code] ?? code
                      return (
                        <div key={`${code}-${index}`} className="flex items-center gap-0">
                          <button
                            type="button"
                            onMouseEnter={() => setHoveredSegmentIndex(index)}
                            onMouseLeave={() => setHoveredSegmentIndex(null)}
                            className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${tagStyle} ${isHovered ? 'ring-2 ring-il-blue/35' : 'opacity-85 hover:opacity-100'}`}
                          >
                            {label}
                          </button>
                          {index < selectedTemplate.sequence.length - 1 ? (
                            <span
                              className="inline-block h-[2px] w-10 rounded-full bg-il-storm-10/90"
                              aria-hidden="true"
                            />
                          ) : null}
                        </div>
                      )
                    })}
                  </div>
                ) : null}
              </header>
              <div className="min-h-0 overflow-y-auto p-4">
                {selectedKey === null ? (
                  <p className="text-sm text-il-storm-60">No result selected yet. Choose a template or no-template generation.</p>
                ) : selectedKey === 'direct' ? (
                  (statusMap.direct ?? 'idle') === 'loading' ? (
                    <LoadingPanel />
                  ) : (
                    <p className="whitespace-pre-wrap leading-8 text-il-storm-10">
                      {directOutput ?? 'Direct result will appear here.'}
                    </p>
                  )
                ) : currentVariant ? (
                  <p className="leading-8 text-il-storm-10">
                    {currentVariant.segments.map((segment: StructuredSegment, index) => {
                      const isHovered = hoveredSegmentIndex === index
                      const blockStyle = SEGMENT_STYLE[segment.label] ?? 'bg-gray-100 text-gray-900 border-gray-200'
                      return (
                        <span
                          key={`${segment.label}-${segment.text}-${index}`}
                          onMouseEnter={() => setHoveredSegmentIndex(index)}
                          onMouseLeave={() => setHoveredSegmentIndex(null)}
                          className={`mr-1 inline rounded px-1.5 py-0.5 box-decoration-clone transition ${blockStyle} ${isHovered ? 'ring-2 ring-il-blue/35' : 'opacity-90 hover:opacity-100'}`}
                        >
                          {segment.text}
                        </span>
                      )
                    })}
                  </p>
                ) : currentStatus === 'loading' ? (
                  <LoadingPanel />
                ) : currentStatus === 'error' ? (
                  <p className="text-sm text-il-altgeld">Generation failed. Click this template again to retry.</p>
                ) : (
                  <p className="text-sm text-il-storm-60">Select a template to generate result.</p>
                )}
              </div>
            </section>
          </section>
        </div>
      </section>
    </div>
  )
}

function LoadingPanel() {
  const loadingSteps = [
    'Analyzing template structure...',
    'Filling sentence content...',
    'Polishing tone and rhythm...',
    'Balancing clarity and persuasion...',
    'Checking sequence consistency...',
    'Refining CTA strength...',
    'Final pass for readability...',
  ]
  const [stepIndex, setStepIndex] = useState(0)

  useEffect(() => {
    const delayMs = 1800 + Math.floor(Math.random() * 500)
    const timeoutId = window.setTimeout(() => {
      setStepIndex((prev) => (prev + 1) % loadingSteps.length)
    }, delayMs)
    return () => window.clearTimeout(timeoutId)
  }, [stepIndex, loadingSteps.length])

  return (
    <div className="flex min-h-[280px] flex-col items-center justify-center gap-5">
      <LoaderCircle className="h-10 w-10 animate-spin text-il-blue" aria-hidden="true" />
      <div className="text-center text-sm text-il-storm-60">
        <p className="mt-2 min-h-[1.5rem] transition-opacity duration-300">{loadingSteps[stepIndex]}</p>
      </div>
    </div>
  )
}
