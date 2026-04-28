import { useState } from 'react'
import { AlertCircle } from 'lucide-react'
import { DirectResult } from '../components/DirectResult'
import { InputPanel } from '../components/InputPanel'
import { VariantTabs } from '../components/VariantTabs'
import { useGenerate } from '../hooks/useGenerate'
import type { GenerateResponse, LengthOption } from '../types/generate'

export function GeneratePage() {
  const generate = useGenerate()
  const [category, setCategory] = useState('tech')
  const [length, setLength] = useState<LengthOption>('m')
  const [productDesc, setProductDesc] = useState('')
  const [generationPrompt, setGenerationPrompt] = useState('')
  const [selectedVariantIndex, setSelectedVariantIndex] = useState(0)
  const [result, setResult] = useState<GenerateResponse | null>(null)

  const submit = async () => {
    const payload = {
      category,
      length,
      product_desc: productDesc.trim(),
      generation_prompt: generationPrompt.trim() || null,
    }
    const response = await generate.mutateAsync(payload)
    setResult(response)
    setSelectedVariantIndex(0)
  }

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] pt-5">
      <header className="rounded-lg border border-il-blue bg-il-blue px-5 py-5 text-white">
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-white/75">Copy Generation</p>
        <h1 className="mt-1 text-3xl font-semibold leading-tight">Generate</h1>
      </header>
      <section className="min-h-0 overflow-y-auto py-5">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
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
            <section className="rounded-lg border border-il-storm-20 bg-white p-4">
              <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-il-blue">Image</h2>
              <button
                type="button"
                disabled
                className="mt-3 h-11 rounded-md border border-il-storm-20 px-4 text-sm font-semibold text-il-storm-40"
              >
                Image generation will be enabled in the next phase
              </button>
            </section>
            {generate.isError ? (
              <div className="rounded-lg border border-il-altgeld bg-white p-4 text-sm text-il-altgeld">
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-4 w-4" aria-hidden="true" />
                  <span>Generation failed. Please try again.</span>
                </div>
              </div>
            ) : null}
          </div>
          <div className="space-y-5">
            <VariantTabs
              variants={result?.structured_variants ?? []}
              selectedIndex={selectedVariantIndex}
              onSelect={setSelectedVariantIndex}
            />
            <DirectResult output={result?.direct_output ?? null} />
          </div>
        </div>
      </section>
    </div>
  )
}
