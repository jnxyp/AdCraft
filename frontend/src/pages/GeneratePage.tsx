import { type MouseEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  Ban,
  Check,
  Copy,
  Eraser,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCcw,
  Scissors,
  Sparkles,
  StretchHorizontal,
  Trash2,
} from 'lucide-react'
import { InputPanel } from '../components/InputPanel'
import { getCategoryDisplayName } from '../constants/categories'
import {
  useApplyTemplateInstructions,
  useFindTemplates,
  useGenerateDirect,
  useGenerateTemplateVariant,
  useRegenerateTemplateFull,
} from '../hooks/useGenerate'
import type {
  CategoryOption,
  FindTemplatesResponse,
  LengthOption,
  SegmentEditInstruction,
  SegmentEditMode,
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

interface SlotLengthState {
  result: FindTemplatesResponse | null
  resolvedCategory: string | null
  selectedKey: ResultKey
  variantMap: Record<string, StructuredVariant>
  statusMap: Record<string, GenerationStatus>
  directOutput: string | null
  editInstructionsMap: Record<string, SegmentEditInstruction[]>
}

interface SlotData {
  id: string
  title: string
  productDesc: string
  generationPrompt: string
  category: CategoryOption
  lastLength: LengthOption
  updatedAt: string
  createdAt: string
  byLength: Partial<Record<LengthOption, SlotLengthState>>
  lastSearchSignature: string | null
}

const DEFAULT_SLOT_TITLE = 'New Ad Copy'
const TITLE_LIMIT = 24
const SESSION_ID_KEY = 'adcraft_session_id'
const EXPLAIN_VISIBILITY_KEY_PREFIX = 'adcraft_explain_visibility_'
const GENERATE_CACHE_SCHEMA_VERSION = '3'
const GENERATE_CACHE_SCHEMA_KEY = 'adcraft_generate_cache_schema_version'
const GENERATION_TIMEOUT_MS = 25000

function isLengthOption(value: string | null): value is LengthOption {
  return value === 'xs' || value === 's' || value === 'm' || value === 'l' || value === 'xl'
}

function defaultLengthState(): SlotLengthState {
  return {
    result: null,
    resolvedCategory: null,
    selectedKey: null,
    variantMap: {},
    statusMap: {},
    directOutput: null,
    editInstructionsMap: {},
  }
}

function createDefaultSlot(now: string): SlotData {
  return {
    id: crypto.randomUUID(),
    title: DEFAULT_SLOT_TITLE,
    productDesc: '',
    generationPrompt: '',
    category: 'auto',
    lastLength: 's',
    updatedAt: now,
    createdAt: now,
    byLength: {},
    lastSearchSignature: null,
  }
}

function nextDefaultSlotTitle(slots: SlotData[]): string {
  const pattern = /^New Ad Copy(?: (\d+))?$/
  let maxIndex = 0
  for (const slot of slots) {
    const match = slot.title.match(pattern)
    if (!match) {
      continue
    }
    const index = match[1] ? Number(match[1]) : 1
    if (Number.isFinite(index)) {
      maxIndex = Math.max(maxIndex, index)
    }
  }
  if (maxIndex <= 0) {
    return DEFAULT_SLOT_TITLE
  }
  return `${DEFAULT_SLOT_TITLE} ${maxIndex + 1}`
}

function nextCopiedSlotTitle(sourceTitle: string, slots: SlotData[]): string {
  const existingTitles = new Set(slots.map((slot) => slot.title))
  const match = sourceTitle.match(/^(.*?)(?: \(Copy(?: (\d+))?\))?$/)
  const baseTitle = match?.[1]?.trim() || sourceTitle
  const currentCopyIndex = match?.[2] ? Number(match[2]) : sourceTitle.endsWith(' (Copy)') ? 1 : 0
  let nextIndex = currentCopyIndex > 0 ? currentCopyIndex + 1 : 1

  while (true) {
    const candidate = nextIndex === 1
      ? `${baseTitle} (Copy)`
      : `${baseTitle} (Copy ${nextIndex})`
    if (!existingTitles.has(candidate)) {
      return candidate
    }
    nextIndex += 1
  }
}

function deriveTitle(productDesc: string): string {
  const trimmed = productDesc.trim()
  if (trimmed.length === 0) {
    return DEFAULT_SLOT_TITLE
  }
  if (trimmed.length <= TITLE_LIMIT) {
    return trimmed
  }
  return `${trimmed.slice(0, TITLE_LIMIT)}...`
}

function getOrCreateSessionId(): string {
  const existing = window.localStorage.getItem(SESSION_ID_KEY)
  if (existing && existing.trim().length > 0) {
    return existing
  }
  const created = crypto.randomUUID()
  window.localStorage.setItem(SESSION_ID_KEY, created)
  return created
}

function clearLegacyGenerateCacheIfNeeded() {
  const current = window.localStorage.getItem(GENERATE_CACHE_SCHEMA_KEY)
  if (current === GENERATE_CACHE_SCHEMA_VERSION) {
    return
  }
  const keys: string[] = []
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index)
    if (key !== null) {
      keys.push(key)
    }
  }
  for (const key of keys) {
    if (key.startsWith('adcraft_generate_slots_') || key.startsWith(EXPLAIN_VISIBILITY_KEY_PREFIX)) {
      window.localStorage.removeItem(key)
    }
  }
  window.localStorage.setItem(GENERATE_CACHE_SCHEMA_KEY, GENERATE_CACHE_SCHEMA_VERSION)
}

function parseGenerateLocation(): { slotId: string | null; length: LengthOption } {
  const path = window.location.pathname
  const prefix = '/generate'
  const slotId = path.startsWith(prefix)
    ? path.slice(prefix.length).replace(/^\//, '').trim() || null
    : null
  const params = new URLSearchParams(window.location.search)
  const lengthParam = params.get('length')
  return {
    slotId,
    length: isLengthOption(lengthParam) ? lengthParam : 's',
  }
}

function formatTime(value: string): string {
  const date = new Date(value)
  const now = new Date()

  const isSameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  if (isSameDay) {
    return new Intl.DateTimeFormat('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(date)
  }

  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const isYesterday =
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate()
  if (isYesterday || date.getFullYear() === now.getFullYear()) {
    return `${date.getMonth() + 1}/${date.getDate()}`
  }

  return `${date.getFullYear()}/${date.getMonth() + 1}`
}

function formatMetricNumber(value: number, fullPrecision = false): string {
  if (!Number.isFinite(value)) {
    return String(value)
  }
  if (!fullPrecision) {
    if (Number.isInteger(value)) {
      return String(value)
    }
    return value.toFixed(3)
  }
  const absolute = Math.abs(value)
  if ((absolute > 0 && absolute < 1e-4) || absolute >= 1e6) {
    return value.toExponential(12)
  }
  return value.toPrecision(15).replace(/(?:\.0+|(\.\d+?)0+)$/, '$1')
}

function getCurrentResultText(
  selectedKey: ResultKey,
  directOutput: string | null,
  currentVariant: StructuredVariant | null,
): string {
  if (selectedKey === 'direct') {
    return directOutput ?? ''
  }
  if (selectedKey && currentVariant) {
    return currentVariant.output
  }
  return ''
}

function defaultInstructionList(sequence: string[]): SegmentEditInstruction[] {
  return sequence.map(() => ({ mode: 'none', prompt: null }))
}

function hasAnyInstruction(items: SegmentEditInstruction[]): boolean {
  return items.some((item) => item.mode !== 'none')
}

function instructionForIndex(
  editMap: Record<string, SegmentEditInstruction[]>,
  templateId: string,
  sequence: string[],
  index: number,
): SegmentEditInstruction {
  const list = editMap[templateId] ?? defaultInstructionList(sequence)
  return list[index] ?? { mode: 'none', prompt: null }
}

function retainDisableInstructions(
  previous: SegmentEditInstruction[] | undefined,
  sequence: string[],
): SegmentEditInstruction[] {
  const next = defaultInstructionList(sequence)
  if (!previous) {
    return next
  }
  for (let index = 0; index < sequence.length; index += 1) {
    if (previous[index]?.mode === 'disable') {
      next[index] = { mode: 'disable', prompt: null }
    }
  }
  return next
}

class GenerationTimeoutError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'GenerationTimeoutError'
  }
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  let timer: number | null = null
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_, reject) => {
        timer = window.setTimeout(() => reject(new GenerationTimeoutError(message)), timeoutMs)
      }),
    ])
  } finally {
    if (timer !== null) {
      window.clearTimeout(timer)
    }
  }
}

export function GeneratePage({ showExplainability }: { showExplainability: boolean }) {
  const findTemplates = useFindTemplates()
  const generateDirect = useGenerateDirect()
  const generateTemplateVariant = useGenerateTemplateVariant()
  const regenerateTemplateFull = useRegenerateTemplateFull()
  const applyTemplateInstructions = useApplyTemplateInstructions()

  const [sessionId] = useState<string>(() => {
    clearLegacyGenerateCacheIfNeeded()
    return getOrCreateSessionId()
  })
  const storageKey = `adcraft_generate_slots_${sessionId}`

  const [{ slots: initialSlots, slotId: initialSlotId, length: initialLength }] = useState(() => {
    const route = parseGenerateLocation()
    const raw = window.localStorage.getItem(`adcraft_generate_slots_${sessionId}`)
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as SlotData[]
        if (Array.isArray(parsed) && parsed.length > 0) {
          const found = route.slotId && parsed.some((item) => item.id === route.slotId)
          return {
            slots: parsed,
            slotId: found ? route.slotId : parsed[0].id,
            length: route.length,
          }
        }
      } catch {
        // fallback below
      }
    }
    const first = createDefaultSlot(new Date().toISOString())
    return { slots: [first], slotId: first.id, length: route.length }
  })

  const [currentSlotId, setCurrentSlotId] = useState<string | null>(initialSlotId)
  const [length, setLength] = useState<LengthOption>(initialLength)
  const [slots, setSlots] = useState<SlotData[]>(initialSlots)
  const [hoveredSegmentIndex, setHoveredSegmentIndex] = useState<number | null>(null)
  const [copied, setCopied] = useState(false)
  const [editMenu, setEditMenu] = useState<{ templateId: string; index: number; x: number; y: number } | null>(null)
  const [segmentPromptModal, setSegmentPromptModal] = useState<{
    templateId: string
    index: number
    value: string
  } | null>(null)
  const [overwriteModal, setOverwriteModal] = useState<{
    templateId: string
    index: number
    mode: SegmentEditMode
  } | null>(null)
  const editMenuRef = useRef<HTMLDivElement | null>(null)

  const cancelEpochRef = useRef(0)

  useEffect(() => {
    if (slots.length > 0) {
      window.localStorage.setItem(storageKey, JSON.stringify(slots))
    }
  }, [slots, storageKey])

  useEffect(() => {
    if (!editMenu) {
      return
    }
    const onPointerDown = (event: MouseEvent | globalThis.MouseEvent) => {
      const target = event.target as Node | null
      if (editMenuRef.current && target && !editMenuRef.current.contains(target)) {
        setEditMenu(null)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [editMenu])

  useEffect(() => {
    const onPopState = () => {
      const parsed = parseGenerateLocation()
      if (parsed.slotId && slots.some((item) => item.id === parsed.slotId)) {
        setCurrentSlotId(parsed.slotId)
      }
      setLength(parsed.length)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [slots])

  const sortedSlots = useMemo(
    () => [...slots].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()),
    [slots],
  )

  const currentSlot = slots.find((slot) => slot.id === currentSlotId) ?? null
  const currentLengthState = currentSlot?.byLength[length] ?? defaultLengthState()

  const updateSlot = (slotId: string, updater: (slot: SlotData) => SlotData) => {
    setSlots((prev) => prev.map((slot) => (slot.id === slotId ? updater(slot) : slot)))
  }

  const updateSlotLengthState = (
    slotId: string,
    lengthKey: LengthOption,
    updater: (state: SlotLengthState) => SlotLengthState,
  ) => {
    updateSlot(slotId, (slot) => {
      const prevState = slot.byLength[lengthKey] ?? defaultLengthState()
      return {
        ...slot,
        byLength: {
          ...slot.byLength,
          [lengthKey]: updater(prevState),
        },
      }
    })
  }

  const syncUrl = (slotId: string, lengthKey: LengthOption, replace = false) => {
    const nextUrl = `/generate/${slotId}?length=${lengthKey}`
    if (replace) {
      window.history.replaceState({}, '', nextUrl)
    } else {
      window.history.pushState({}, '', nextUrl)
    }
  }

  const handleSelectSlot = (slotId: string) => {
    const slot = slots.find((item) => item.id === slotId)
    if (!slot) {
      return
    }
    setCurrentSlotId(slotId)
    setLength(slot.lastLength)
    setHoveredSegmentIndex(null)
    syncUrl(slotId, slot.lastLength)
  }

  const handleAddSlot = () => {
    const next = {
      ...createDefaultSlot(new Date().toISOString()),
      title: nextDefaultSlotTitle(slots),
    }
    setSlots((prev) => [next, ...prev])
    setCurrentSlotId(next.id)
    setLength('s')
    setHoveredSegmentIndex(null)
    syncUrl(next.id, 's')
  }

  const handleCopySlot = (slotId: string) => {
    const source = slots.find((slot) => slot.id === slotId)
    if (!source) {
      return
    }
    const now = new Date().toISOString()
    const copied: SlotData = {
      ...source,
      id: crypto.randomUUID(),
      createdAt: now,
      updatedAt: now,
      title: nextCopiedSlotTitle(source.title, slots),
      byLength: JSON.parse(JSON.stringify(source.byLength)) as Partial<Record<LengthOption, SlotLengthState>>,
      lastSearchSignature: source.lastSearchSignature,
    }
    setSlots((prev) => [copied, ...prev])
    setCurrentSlotId(copied.id)
    setLength(copied.lastLength)
    setHoveredSegmentIndex(null)
    syncUrl(copied.id, copied.lastLength)
  }

  const handleDeleteSlot = (slotId: string) => {
    const target = slots.find((slot) => slot.id === slotId)
    if (!target) {
      return
    }
    if (!window.confirm(`Delete slot "${target.title}"? This cannot be undone.`)) {
      return
    }
    const remaining = slots.filter((slot) => slot.id !== slotId)
    if (remaining.length === 0) {
      const fallback = {
        ...createDefaultSlot(new Date().toISOString()),
        title: nextDefaultSlotTitle(remaining),
      }
      setSlots([fallback])
      setCurrentSlotId(fallback.id)
      setLength('s')
      syncUrl(fallback.id, 's')
      return
    }
    setSlots(remaining)
    if (currentSlotId === slotId) {
      const next = [...remaining].sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      )[0]
      setCurrentSlotId(next.id)
      setLength(next.lastLength)
      syncUrl(next.id, next.lastLength)
    }
  }

  const handleLengthChange = (nextLength: LengthOption) => {
    setLength(nextLength)
    if (!currentSlot) {
      return
    }
    updateSlot(currentSlot.id, (slot) => ({ ...slot, lastLength: nextLength }))
    syncUrl(currentSlot.id, nextLength)
  }

  const submit = async () => {
    if (!currentSlot) {
      return
    }

    const trimmedProduct = currentSlot.productDesc.trim()
    const trimmedPrompt = currentSlot.generationPrompt.trim()

    const nextSignature = JSON.stringify({
      productDesc: trimmedProduct,
      generationPrompt: trimmedPrompt,
      category: currentSlot.category,
    })
    const ruleAChanged =
      currentSlot.lastSearchSignature !== null && currentSlot.lastSearchSignature !== nextSignature

    if (ruleAChanged) {
      cancelEpochRef.current += 1
      updateSlot(currentSlot.id, (slot) => ({
        ...slot,
        productDesc: trimmedProduct,
        generationPrompt: trimmedPrompt,
        title: deriveTitle(trimmedProduct),
        updatedAt: new Date().toISOString(),
        byLength: {},
        lastSearchSignature: nextSignature,
      }))
    } else {
      updateSlot(currentSlot.id, (slot) => ({
        ...slot,
        productDesc: trimmedProduct,
        generationPrompt: trimmedPrompt,
        title: deriveTitle(trimmedProduct),
        updatedAt: new Date().toISOString(),
        lastSearchSignature: nextSignature,
      }))
    }

    const payload = {
      category: currentSlot.category,
      length,
      product_desc: trimmedProduct,
      generation_prompt: trimmedPrompt || null,
    }

    const epoch = cancelEpochRef.current
    const response = await findTemplates.mutateAsync(payload)
    if (epoch !== cancelEpochRef.current) {
      return
    }

    updateSlot(currentSlot.id, (slot) => ({
      ...slot,
      updatedAt: new Date().toISOString(),
      lastLength: length,
    }))

    const topThreeIds = response.templates.slice(0, 3).map((template) => template.template_id)
    const nextStatus: Record<string, GenerationStatus> = { direct: 'loading' }
    for (const templateId of topThreeIds) {
      nextStatus[templateId] = 'loading'
    }

    updateSlotLengthState(currentSlot.id, length, () => ({
      result: response,
      resolvedCategory: response.category,
      selectedKey: response.templates[0]?.template_id ?? null,
      variantMap: {},
      statusMap: nextStatus,
      directOutput: null,
      editInstructionsMap: {},
    }))

    for (const template of response.templates.slice(0, 3)) {
      void generateTemplateFor(
        epoch,
        currentSlot.id,
        length,
        template,
        response.category,
        response.product_desc,
        response.length,
        payload.generation_prompt,
      )
    }

    void generateDirectOutput(
      epoch,
      currentSlot.id,
      length,
      response.category as CategoryOption,
      response.product_desc,
      response.length,
      payload.generation_prompt,
    )
  }

  const generateTemplateFor = async (
    epoch: number,
    slotId: string,
    lengthKey: LengthOption,
    template: TemplateCandidate,
    categoryForGeneration: string,
    productDescForGeneration: string,
    lengthForGeneration: LengthOption,
    promptForGeneration: string | null,
  ) => {
    updateSlotLengthState(slotId, lengthKey, (prev) => ({
      ...prev,
      statusMap: { ...prev.statusMap, [template.template_id]: 'loading' },
    }))
    try {
      const variant = await withTimeout(
        generateTemplateVariant.mutateAsync({
          template_id: template.template_id,
          category: categoryForGeneration,
          product_desc: productDescForGeneration,
          length: lengthForGeneration,
          generation_prompt: promptForGeneration,
        }),
        GENERATION_TIMEOUT_MS,
        `Template ${template.template_id} generation timed out`,
      )
      if (epoch !== cancelEpochRef.current) {
        return
      }
      updateSlotLengthState(slotId, lengthKey, (prev) => ({
        ...prev,
        variantMap: { ...prev.variantMap, [template.template_id]: variant },
        statusMap: { ...prev.statusMap, [template.template_id]: 'done' },
        editInstructionsMap: {
          ...prev.editInstructionsMap,
          [template.template_id]:
            prev.editInstructionsMap[template.template_id] ?? defaultInstructionList(variant.sequence),
        },
      }))
      updateSlot(slotId, (slot) => ({ ...slot, updatedAt: new Date().toISOString() }))
    } catch (error) {
      if (epoch !== cancelEpochRef.current) {
        return
      }
      if (error instanceof GenerationTimeoutError) {
        updateSlotLengthState(slotId, lengthKey, (prev) => ({
          ...prev,
          statusMap: { ...prev.statusMap, [template.template_id]: 'idle' },
        }))
      } else {
        updateSlotLengthState(slotId, lengthKey, (prev) => ({
          ...prev,
          statusMap: { ...prev.statusMap, [template.template_id]: 'error' },
        }))
      }
    }
  }

  const generateDirectOutput = async (
    epoch: number,
    slotId: string,
    lengthKey: LengthOption,
    selectedCategory: CategoryOption,
    selectedProductDesc: string,
    selectedLength: LengthOption,
    selectedPrompt: string | null,
  ) => {
    updateSlotLengthState(slotId, lengthKey, (prev) => ({
      ...prev,
      statusMap: { ...prev.statusMap, direct: 'loading' },
    }))
    try {
      const response = await withTimeout(
        generateDirect.mutateAsync({
          category: selectedCategory,
          product_desc: selectedProductDesc,
          length: selectedLength,
          generation_prompt: selectedPrompt,
        }),
        GENERATION_TIMEOUT_MS,
        'Direct generation timed out',
      )
      if (epoch !== cancelEpochRef.current) {
        return
      }
      updateSlotLengthState(slotId, lengthKey, (prev) => ({
        ...prev,
        directOutput: response.output,
        statusMap: { ...prev.statusMap, direct: 'done' },
      }))
      updateSlot(slotId, (slot) => ({ ...slot, updatedAt: new Date().toISOString() }))
    } catch (error) {
      if (epoch !== cancelEpochRef.current) {
        return
      }
      if (error instanceof GenerationTimeoutError) {
        updateSlotLengthState(slotId, lengthKey, (prev) => ({
          ...prev,
          directOutput: null,
          statusMap: { ...prev.statusMap, direct: 'idle' },
        }))
      } else {
        updateSlotLengthState(slotId, lengthKey, (prev) => ({
          ...prev,
          statusMap: { ...prev.statusMap, direct: 'error' },
        }))
      }
    }
  }

  const selectTemplate = async (template: TemplateCandidate) => {
    if (!currentSlot) {
      return
    }
    updateSlotLengthState(currentSlot.id, length, (prev) => ({
      ...prev,
      selectedKey: template.template_id,
    }))

    const state = currentSlot.byLength[length] ?? defaultLengthState()
    if (state.variantMap[template.template_id] !== undefined || state.result === null || state.resolvedCategory === null) {
      return
    }

    const epoch = cancelEpochRef.current
    await generateTemplateFor(
      epoch,
      currentSlot.id,
      length,
      template,
      state.resolvedCategory,
      state.result.product_desc,
      state.result.length,
      currentSlot.generationPrompt.trim() || null,
    )
  }

  const currentVariant: StructuredVariant | null =
    currentLengthState.selectedKey === null || currentLengthState.selectedKey === 'direct'
      ? null
      : (currentLengthState.variantMap[currentLengthState.selectedKey] ?? null)

  const selectedTemplate = currentLengthState.selectedKey === null || currentLengthState.selectedKey === 'direct'
    ? null
    : (currentLengthState.result?.templates.find((template) => template.template_id === currentLengthState.selectedKey) ?? null)
  const currentStatus = currentLengthState.selectedKey
    ? currentLengthState.statusMap[currentLengthState.selectedKey] ?? 'idle'
    : 'idle'
  const currentResultText = getCurrentResultText(
    currentLengthState.selectedKey,
    currentLengthState.directOutput,
    currentVariant,
  )
  const currentTemplateInstructions =
    currentVariant && selectedTemplate
      ? (currentLengthState.editInstructionsMap[selectedTemplate.template_id] ??
          defaultInstructionList(currentVariant.sequence))
      : []
  const hasTemplateInstructions = hasAnyInstruction(currentTemplateInstructions)
  const isTemplateGenerating = selectedTemplate !== null && currentStatus === 'loading'

  const setTemplateInstruction = (
    templateId: string,
    sequence: string[],
    index: number,
    nextMode: SegmentEditMode,
    nextPrompt: string | null,
  ) => {
    if (!currentSlot) {
      return
    }
    updateSlotLengthState(currentSlot.id, length, (prev) => {
      const list = [...(prev.editInstructionsMap[templateId] ?? defaultInstructionList(sequence))]
      list[index] = { mode: nextMode, prompt: nextPrompt }
      return {
        ...prev,
        editInstructionsMap: {
          ...prev.editInstructionsMap,
          [templateId]: list,
        },
      }
    })
  }

  const regenerateAllForSelectedTemplate = async () => {
    if (!currentSlot || !selectedTemplate || !currentVariant || !currentLengthState.result) {
      return
    }
    updateSlotLengthState(currentSlot.id, length, (prev) => ({
      ...prev,
      statusMap: { ...prev.statusMap, [selectedTemplate.template_id]: 'loading' },
    }))
    try {
      const response = await regenerateTemplateFull.mutateAsync({
        template_id: selectedTemplate.template_id,
        category: currentLengthState.result.category,
        product_desc: currentLengthState.result.product_desc,
        length: currentLengthState.result.length,
        generation_prompt: currentSlot.generationPrompt.trim() || null,
      })
      updateSlotLengthState(currentSlot.id, length, (prev) => ({
        ...prev,
        variantMap: { ...prev.variantMap, [selectedTemplate.template_id]: response },
        editInstructionsMap: {
          ...prev.editInstructionsMap,
          [selectedTemplate.template_id]: retainDisableInstructions(
            prev.editInstructionsMap[selectedTemplate.template_id],
            response.sequence,
          ),
        },
        statusMap: { ...prev.statusMap, [selectedTemplate.template_id]: 'done' },
      }))
    } catch {
      updateSlotLengthState(currentSlot.id, length, (prev) => ({
        ...prev,
        statusMap: { ...prev.statusMap, [selectedTemplate.template_id]: 'error' },
      }))
    }
  }

  const applyInstructionsForSelectedTemplate = async () => {
    if (!currentSlot || !selectedTemplate || !currentVariant || !currentLengthState.result) {
      return
    }
    const instructions =
      currentLengthState.editInstructionsMap[selectedTemplate.template_id] ??
      defaultInstructionList(currentVariant.sequence)
    if (!hasAnyInstruction(instructions)) {
      return
    }
    updateSlotLengthState(currentSlot.id, length, (prev) => ({
      ...prev,
      statusMap: { ...prev.statusMap, [selectedTemplate.template_id]: 'loading' },
    }))
    try {
      const response = await applyTemplateInstructions.mutateAsync({
        template_id: selectedTemplate.template_id,
        category: currentLengthState.result.category,
        product_desc: currentLengthState.result.product_desc,
        length: currentLengthState.result.length,
        generation_prompt: currentSlot.generationPrompt.trim() || null,
        current_segments: currentVariant.segments,
        instructions,
      })
      updateSlotLengthState(currentSlot.id, length, (prev) => ({
        ...prev,
        variantMap: { ...prev.variantMap, [selectedTemplate.template_id]: response },
        editInstructionsMap: {
          ...prev.editInstructionsMap,
          [selectedTemplate.template_id]: retainDisableInstructions(
            prev.editInstructionsMap[selectedTemplate.template_id],
            response.sequence,
          ),
        },
        statusMap: { ...prev.statusMap, [selectedTemplate.template_id]: 'done' },
      }))
    } catch {
      updateSlotLengthState(currentSlot.id, length, (prev) => ({
        ...prev,
        statusMap: { ...prev.statusMap, [selectedTemplate.template_id]: 'error' },
      }))
    }
  }

  const openEditMenu = (event: MouseEvent<HTMLButtonElement>, templateId: string, index: number) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const menuWidth = 220
    const menuHeight = 192
    const gap = 6
    const maxX = window.innerWidth - menuWidth - 8
    const maxY = window.innerHeight - menuHeight - 8
    const preferredX = rect.right + gap
    const fallbackX = rect.left - menuWidth - gap
    const x = preferredX <= maxX ? preferredX : Math.max(8, fallbackX)
    const y = Math.min(Math.max(8, rect.top), Math.max(8, maxY))
    setEditMenu({
      templateId,
      index,
      x,
      y,
    })
  }

  const runMenuAction = (mode: SegmentEditMode, source: { templateId: string; index: number }) => {
    if (!selectedTemplate) {
      return
    }
    if (mode === 'regenerate') {
      setSegmentPromptModal({
        templateId: source.templateId,
        index: source.index,
        value: '',
      })
      return
    }
    if (mode === 'disable') {
      const current = instructionForIndex(
        currentLengthState.editInstructionsMap,
        selectedTemplate.template_id,
        selectedTemplate.sequence,
        source.index,
      )
      const nextMode: SegmentEditMode = current.mode === 'disable' ? 'none' : 'disable'
      setTemplateInstruction(source.templateId, selectedTemplate.sequence, source.index, nextMode, null)
      return
    }
    setTemplateInstruction(source.templateId, selectedTemplate.sequence, source.index, mode, null)
  }

  const clearMenuAction = (source: { templateId: string; index: number }) => {
    if (!selectedTemplate) {
      return
    }
    setTemplateInstruction(source.templateId, selectedTemplate.sequence, source.index, 'none', null)
  }

  const applyMenuAction = (mode: SegmentEditMode) => {
    if (!editMenu || !selectedTemplate) {
      return
    }
    const currentInstruction = instructionForIndex(
      currentLengthState.editInstructionsMap,
      selectedTemplate.template_id,
      selectedTemplate.sequence,
      editMenu.index,
    )
    const overwrite =
      currentInstruction.mode !== 'none' &&
      !(mode === 'disable' && currentInstruction.mode === 'disable')
    setEditMenu(null)
    if (overwrite) {
      setOverwriteModal({
        templateId: editMenu.templateId,
        index: editMenu.index,
        mode,
      })
      return
    }
    runMenuAction(mode, editMenu)
  }

  const copyCurrentResult = async () => {
    if (currentResultText.trim().length === 0) {
      return
    }
    await navigator.clipboard.writeText(currentResultText)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1200)
  }

  return (
    <div className="flex h-full min-h-0 items-stretch gap-[10px]">
      <aside className="flex h-full min-h-0 w-[20vw] shrink-0 select-none flex-col rounded-lg border border-il-storm-20 bg-white p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-[0.1em] text-il-storm-60">Copy Sessions</div>
        <div className="flex-1 space-y-2 overflow-y-auto pr-1">
          {sortedSlots.map((slot) => {
            const active = slot.id === currentSlotId
            return (
              <div
                key={slot.id}
                className={
                  active
                    ? 'rounded-md border border-il-blue bg-il-blue/10 p-2'
                    : 'rounded-md border border-il-storm-20 bg-white p-2'
                }
              >
                <div className="flex items-start justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => handleSelectSlot(slot.id)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <p
                      className="truncate pr-2 text-sm font-semibold text-il-storm-10"
                      title={slot.title}
                    >
                      {slot.title}
                    </p>
                    <p className="mt-1 text-xs text-il-storm-60">
                      {getCategoryDisplayName(slot.category)} · {slot.lastLength.toUpperCase()}
                    </p>
                  </button>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className="text-xs text-il-storm-40">{formatTime(slot.updatedAt)}</span>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => handleCopySlot(slot.id)}
                        className="rounded p-1 text-il-storm-50 hover:bg-white hover:text-il-blue"
                        aria-label={`Copy ${slot.title}`}
                      >
                        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteSlot(slot.id)}
                        className="rounded p-1 text-il-storm-50 hover:bg-white hover:text-il-altgeld"
                        aria-label={`Delete ${slot.title}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        <button
          type="button"
          onClick={handleAddSlot}
          className="mt-3 inline-flex h-10 items-center justify-center rounded-md border-2 border-il-blue bg-white text-il-blue transition hover:bg-il-blue hover:text-white"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
        </button>
      </aside>

      <div className="flex h-full min-h-0 flex-1 self-stretch flex-col gap-[10px]">
        <section className="shrink-0">
          <div>
            {currentSlot ? (
              <InputPanel
                category={currentSlot.category}
                productDesc={currentSlot.productDesc}
                generationPrompt={currentSlot.generationPrompt}
                length={length}
                disabled={findTemplates.isPending}
                onCategoryChange={(value) => updateSlot(currentSlot.id, (slot) => ({ ...slot, category: value }))}
                onProductDescChange={(value) => updateSlot(currentSlot.id, (slot) => ({ ...slot, productDesc: value }))}
                onGenerationPromptChange={(value) => updateSlot(currentSlot.id, (slot) => ({ ...slot, generationPrompt: value }))}
                onLengthChange={handleLengthChange}
                onSubmit={() => {
                  void submit()
                }}
                footerLeft={
                  <button
                    type="button"
                    onClick={() => handleCopySlot(currentSlot.id)}
                    className="inline-flex h-9 items-center gap-1.5 rounded-md border border-il-storm-20 bg-white px-4 text-sm font-semibold text-il-storm-60 transition hover:border-il-blue hover:text-il-blue"
                  >
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    Fork New Session
                  </button>
                }
              />
            ) : null}
          </div>
        </section>

        {findTemplates.isError ? (
          <div className="shrink-0 rounded-lg border border-il-altgeld bg-white p-4 text-sm text-il-altgeld">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              <span>Template search failed. Please try again.</span>
            </div>
          </div>
        ) : null}

        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-il-storm-20 bg-white lg:flex-row">
              <aside className="flex min-h-0 shrink-0 flex-col border-b border-il-storm-20 lg:w-[340px] lg:border-b-0 lg:border-r lg:border-r-il-storm-20">
                <header className="border-b border-il-storm-20 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-il-storm-60">
                    Search Summary
                  </p>
                  <p className="mt-1 text-base font-semibold text-il-blue">
                    {currentLengthState.result !== null && currentLengthState.resolvedCategory !== null
                      ? `${currentLengthState.result.templates.length} results · ${getCategoryDisplayName(currentLengthState.resolvedCategory)}`
                      : '-'}
                  </p>
                </header>
                <div className="min-h-0 overflow-y-auto p-2">
                  {(currentLengthState.result?.templates ?? []).map((template) => (
                    <button
                      key={template.template_id}
                      type="button"
                      onClick={() => {
                        void selectTemplate(template)
                      }}
                      className={
                        currentLengthState.selectedKey === template.template_id
                          ? 'mb-2 w-full rounded-md border border-il-blue bg-il-blue px-3 py-3 text-left text-white'
                          : 'mb-2 w-full rounded-md border border-il-blue bg-white px-3 py-3 text-left text-il-blue hover:bg-il-blue hover:text-white active:bg-il-blue active:text-white'
                      }
                    >
                      <div className="flex items-start gap-3">
                        <span className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center">
                          {(currentLengthState.statusMap[template.template_id] ?? 'idle') === 'loading' ? (
                            <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                          ) : (currentLengthState.statusMap[template.template_id] ?? 'idle') === 'done' ? (
                            <Check className="h-4 w-4" aria-hidden="true" />
                          ) : null}
                        </span>
                        <p className="min-w-0 flex-1 whitespace-normal break-words text-sm font-semibold">
                          {template.template_name}
                        </p>
                      </div>
                    </button>
                  ))}
                  {currentLengthState.result !== null ? (
                    <button
                      type="button"
                      onClick={() => updateSlotLengthState(currentSlot!.id, length, (prev) => ({ ...prev, selectedKey: 'direct' }))}
                      className={
                        currentLengthState.selectedKey === 'direct'
                          ? 'mb-2 w-full rounded-md border border-il-blue bg-il-blue px-3 py-3 text-left text-white'
                          : (currentLengthState.statusMap.direct ?? 'idle') === 'done'
                            ? 'mb-2 w-full rounded-md border border-il-storm-10 bg-white px-3 py-3 text-left text-il-storm-10 hover:bg-il-storm-10 hover:text-white active:bg-il-storm-10 active:text-white'
                            : 'mb-2 w-full rounded-md border border-il-blue bg-white px-3 py-3 text-left text-il-blue hover:bg-il-blue hover:text-white active:bg-il-blue active:text-white'
                      }
                    >
                      <div className="flex items-start gap-3">
                        <span className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center">
                          {(currentLengthState.statusMap.direct ?? 'idle') === 'loading' ? (
                            <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                          ) : (currentLengthState.statusMap.direct ?? 'idle') === 'done' ? (
                            <Check className="h-4 w-4" aria-hidden="true" />
                          ) : null}
                        </span>
                        <p className="min-w-0 flex-1 whitespace-normal break-words text-sm font-semibold">
                          No-template generation
                        </p>
                      </div>
                    </button>
                  ) : null}
                </div>
              </aside>

              <section className="flex min-h-0 flex-1 flex-col">
                <header className="border-b border-il-storm-20 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-semibold uppercase tracking-[0.1em] text-il-blue">
                      {currentLengthState.selectedKey === null
                        ? 'No Result Selected'
                        : currentLengthState.selectedKey === 'direct'
                          ? 'Direct Result'
                          : 'Template'}
                    </p>
                    {showExplainability && selectedTemplate ? (
                      <div className="flex flex-wrap justify-end gap-1">
                        {(() => {
                          const hasBTScore =
                            selectedTemplate.bt_score !== null &&
                            selectedTemplate.bt_score !== undefined
                          return (
                            <>
                        <MetricBadge short="SD" value={selectedTemplate.semantic_distance ?? null} title="Semantic Distance: lower means more semantically similar to query." />
                        <MetricBadge
                          short="SR"
                          value={selectedTemplate.semantic_rank}
                          title="Semantic Rank: position in raw semantic retrieval before reranking."
                        />
                        <MetricBadge
                          short="L"
                          value={selectedTemplate.sequence.length}
                          title="Template sequence length (number of structure steps)."
                        />
                        <MetricBadge
                          short="BT"
                          value={selectedTemplate.bt_score ?? null}
                          title="Bradley Terry score learned from evaluation votes."
                          fullPrecision
                        />
                        <MetricBadge
                          short="FQ"
                          value={selectedTemplate.freq_score}
                          title="Template frequency prior score from dataset."
                          fullPrecision
                          strikeThrough={hasBTScore}
                        />
                        <MetricBadge
                          short="FS"
                          value={selectedTemplate.final_score ?? selectedTemplate.bt_score ?? selectedTemplate.freq_score}
                          title="Final ranking score used in current ordering."
                          fullPrecision
                        />
                        <MetricBadge
                          short="FR"
                          value={selectedTemplate.final_rank}
                          title="Final rank after reranking."
                        />
                            </>
                          )
                        })()}
                      </div>
                    ) : null}
                  </div>
                  {selectedTemplate ? (
                    <div className="mt-3 flex flex-wrap items-center gap-0">
                      {selectedTemplate.sequence.map((code, index) => {
                        const isHovered = hoveredSegmentIndex === index
                        const tagStyle = SEGMENT_STYLE[code] ?? 'bg-gray-100 text-gray-900 border-gray-200'
                        const label = currentVariant?.segments[index]?.label_full ?? PATTERN_FULL_LABEL[code] ?? code
                        const instruction = instructionForIndex(
                          currentLengthState.editInstructionsMap,
                          selectedTemplate.template_id,
                          selectedTemplate.sequence,
                          index,
                        )
                        const isDisabled = instruction.mode === 'disable'
                        const isEdited = instruction.mode !== 'none'
                        return (
                          <div key={`${code}-${index}`} className="flex items-center gap-0">
                            <div
                              onMouseEnter={() => setHoveredSegmentIndex(index)}
                              onMouseLeave={() => setHoveredSegmentIndex(null)}
                              className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-semibold transition ${tagStyle} ${isHovered ? 'ring-2 ring-il-blue/35' : 'opacity-85 hover:opacity-100'} ${isDisabled ? 'line-through opacity-50' : ''} ${isEdited ? 'border-2 border-il-orange' : ''}`}
                            >
                              {label}
                              <button
                                type="button"
                                disabled={!currentVariant || currentStatus !== 'done' || isTemplateGenerating}
                                onClick={(event) => openEditMenu(event, selectedTemplate.template_id, index)}
                                className="inline-flex h-4 w-4 cursor-pointer items-center justify-center bg-transparent text-il-storm-60 hover:text-il-blue disabled:cursor-not-allowed disabled:opacity-30"
                                aria-label={`Edit ${label}`}
                              >
                                <Pencil className="h-3 w-3" aria-hidden="true" />
                              </button>
                            </div>
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
                  {currentLengthState.selectedKey !== null ? (
                    <div className="mb-4 flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold uppercase tracking-[0.1em] text-il-blue">
                        Generation Result
                      </p>
                      <div className="flex items-center gap-2">
                        <div>
                          <button
                            type="button"
                            onClick={() => {
                              void regenerateAllForSelectedTemplate()
                            }}
                            disabled={!selectedTemplate || !currentVariant || isTemplateGenerating}
                            title="Create a fresh full rewrite."
                            className="inline-flex h-7 items-center gap-1 rounded-md border border-il-storm-20 bg-white px-2.5 text-xs font-semibold text-il-storm-60 transition hover:border-il-blue hover:text-il-blue disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" />
                            Regenerate All
                          </button>
                        </div>
                        <div>
                          <button
                            type="button"
                            onClick={() => {
                              void applyInstructionsForSelectedTemplate()
                            }}
                            disabled={!selectedTemplate || !currentVariant || !hasTemplateInstructions || isTemplateGenerating}
                            title="Apply only section edits."
                            className="inline-flex h-7 items-center gap-1 rounded-md border border-il-storm-20 bg-white px-2.5 text-xs font-semibold text-il-storm-60 transition hover:border-il-blue hover:text-il-blue disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                            Apply Instructions
                          </button>
                        </div>
                        <div>
                          <button
                            type="button"
                            onClick={() => {
                              void copyCurrentResult()
                            }}
                            disabled={currentResultText.trim().length === 0 || isTemplateGenerating}
                            title="Copy current text output."
                            className="inline-flex h-7 items-center gap-1 rounded-md border border-il-storm-20 bg-white px-2.5 text-xs font-semibold text-il-storm-60 transition hover:border-il-blue hover:text-il-blue disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {copied ? (
                              <>
                                <Check className="h-3.5 w-3.5" aria-hidden="true" />
                                Copied
                              </>
                            ) : (
                              <>
                                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                                Copy
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : null}
                  {currentLengthState.selectedKey === null ? (
                    <p className="text-sm text-il-storm-60">No result selected yet. Choose a template or no-template generation.</p>
                  ) : currentLengthState.selectedKey === 'direct' ? (
                    (currentLengthState.statusMap.direct ?? 'idle') === 'loading' ? (
                      <LoadingPanel />
                    ) : (
                      <p className="whitespace-pre-wrap leading-8 text-il-storm-10">
                        {currentLengthState.directOutput ?? 'Direct result will appear here.'}
                      </p>
                    )
                  ) : currentStatus === 'loading' ? (
                    <LoadingPanel sequence={selectedTemplate?.sequence ?? null} />
                  ) : currentVariant ? (
                    <p className="leading-8 text-il-storm-10">
                      {currentVariant.segments.map((segment: StructuredSegment, index) => {
                        const isHovered = hoveredSegmentIndex === index
                        const blockStyle = SEGMENT_STYLE[segment.label] ?? 'bg-gray-100 text-gray-900 border-gray-200'
                        const instruction = selectedTemplate
                          ? instructionForIndex(
                              currentLengthState.editInstructionsMap,
                              selectedTemplate.template_id,
                              selectedTemplate.sequence,
                              index,
                            )
                          : { mode: 'none' as SegmentEditMode, prompt: null }
                        const isDisabled = instruction.mode === 'disable'
                        const isEdited = instruction.mode !== 'none'
                        if (isDisabled) {
                          return null
                        }
                        return (
                          <span key={`${segment.label}-${segment.text}-${index}`} className="mr-1 inline align-middle">
                            <span
                              onMouseEnter={() => setHoveredSegmentIndex(index)}
                              onMouseLeave={() => setHoveredSegmentIndex(null)}
                              className={`inline rounded px-1.5 py-0.5 box-decoration-clone transition ${blockStyle} ${isHovered ? 'ring-2 ring-il-blue/35' : 'opacity-90 hover:opacity-100'} ${isDisabled ? 'line-through opacity-50' : ''} ${isEdited ? 'border border-il-orange' : ''}`}
                            >
                              {segment.text}
                              {selectedTemplate ? (
                                <button
                                  type="button"
                                  disabled={!currentVariant || currentStatus !== 'done' || isTemplateGenerating}
                                  onClick={(event) => openEditMenu(event, selectedTemplate.template_id, index)}
                                  className="-translate-y-[1px] ml-1 inline-flex h-4 w-4 cursor-pointer items-center justify-center bg-transparent align-middle text-il-storm-60 transition-transform hover:text-il-blue disabled:cursor-not-allowed disabled:opacity-30"
                                  aria-label={`Edit ${segment.label_full}`}
                                >
                                  <Pencil className="h-3 w-3" aria-hidden="true" />
                                </button>
                              ) : null}
                            </span>
                          </span>
                        )
                      })}
                    </p>
                  ) : currentStatus === 'error' ? (
                    <p className="text-sm text-il-altgeld">Generation failed. Click this template again to retry.</p>
                  ) : (
                    <p className="text-sm text-il-storm-60">Select a template to generate result.</p>
                  )}
                  {editMenu && selectedTemplate ? (
                    <div
                      ref={editMenuRef}
                      className="fixed z-40 inline-flex flex-col rounded-md border border-il-storm-20 bg-white p-1 shadow-lg"
                      style={{ left: `${editMenu.x}px`, top: `${editMenu.y}px` }}
                    >
                      <button
                        type="button"
                        onClick={() => applyMenuAction('disable')}
                        className={`inline-flex items-center gap-2 rounded px-2 py-1 text-left text-xs font-semibold ${
                          instructionForIndex(
                            currentLengthState.editInstructionsMap,
                            selectedTemplate.template_id,
                            selectedTemplate.sequence,
                            editMenu.index,
                          ).mode === 'disable'
                            ? 'text-emerald-700 hover:bg-emerald-50'
                            : 'text-il-altgeld hover:bg-rose-50'
                        }`}
                      >
                        {instructionForIndex(
                          currentLengthState.editInstructionsMap,
                          selectedTemplate.template_id,
                          selectedTemplate.sequence,
                          editMenu.index,
                        ).mode === 'disable'
                          ? (
                            <>
                              <Check className="h-3.5 w-3.5" aria-hidden="true" />
                              Enable this section
                            </>
                          ) : (
                            <>
                              <Ban className="h-3.5 w-3.5" aria-hidden="true" />
                              Disable this section
                            </>
                          )}
                      </button>
                      <button
                        type="button"
                        onClick={() => applyMenuAction('regenerate')}
                        className="inline-flex items-center gap-2 rounded px-2 py-1 text-left text-xs font-semibold text-il-blue hover:bg-sky-50"
                      >
                        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                        Regenerate this section
                      </button>
                      <button
                        type="button"
                        onClick={() => applyMenuAction('longer')}
                        className="inline-flex items-center gap-2 rounded px-2 py-1 text-left text-xs font-semibold text-emerald-700 hover:bg-emerald-50"
                      >
                        <StretchHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
                        Make it longer
                      </button>
                      <button
                        type="button"
                        onClick={() => applyMenuAction('shorter')}
                        className="inline-flex items-center gap-2 rounded px-2 py-1 text-left text-xs font-semibold text-amber-700 hover:bg-amber-50"
                      >
                        <Scissors className="h-3.5 w-3.5" aria-hidden="true" />
                        Make it shorter
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          clearMenuAction(editMenu)
                          setEditMenu(null)
                        }}
                        className="inline-flex items-center gap-2 rounded px-2 py-1 text-left text-xs font-semibold text-il-storm-60 hover:bg-il-storm-95"
                      >
                        <Eraser className="h-3.5 w-3.5" aria-hidden="true" />
                        Clear edit instruction
                      </button>
                    </div>
                  ) : null}
                </div>
              </section>
            </section>
        
      </div>
      {overwriteModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-sm rounded-lg border border-il-storm-20 bg-white p-4 shadow-xl">
            <p className="text-sm font-semibold uppercase tracking-[0.1em] text-il-blue">Replace Existing Instruction</p>
            <p className="mt-2 text-sm text-il-storm-60">This section already has an instruction. Replace it?</p>
            <div className="mt-3 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setOverwriteModal(null)}
                className="inline-flex h-8 items-center rounded-md border border-il-storm-20 bg-white px-3 text-xs font-semibold text-il-storm-60 hover:border-il-blue hover:text-il-blue"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  runMenuAction(overwriteModal.mode, overwriteModal)
                  setOverwriteModal(null)
                }}
                className="inline-flex h-8 items-center rounded-md border border-il-blue bg-il-blue px-3 text-xs font-semibold text-white"
              >
                Replace
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {segmentPromptModal && selectedTemplate ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-lg border border-il-storm-20 bg-white p-4 shadow-xl">
            <p className="text-sm font-semibold uppercase tracking-[0.1em] text-il-blue">Regenerate Section</p>
            <p className="mt-2 text-xs text-il-storm-60">Optional prompt for this segment (can be empty).</p>
            <textarea
              value={segmentPromptModal.value}
              onChange={(event) =>
                setSegmentPromptModal((prev) => (prev ? { ...prev, value: event.target.value } : prev))
              }
              className="mt-3 h-24 w-full rounded-md border border-il-storm-20 px-3 py-2 text-sm leading-6 focus:border-il-blue focus:outline-none"
            />
            <div className="mt-3 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setSegmentPromptModal(null)}
                className="inline-flex h-8 items-center rounded-md border border-il-storm-20 bg-white px-3 text-xs font-semibold text-il-storm-60 hover:border-il-blue hover:text-il-blue"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  setTemplateInstruction(
                    segmentPromptModal.templateId,
                    selectedTemplate.sequence,
                    segmentPromptModal.index,
                    'regenerate',
                    segmentPromptModal.value.trim().length > 0 ? segmentPromptModal.value.trim() : null,
                  )
                  setSegmentPromptModal(null)
                }}
                className="inline-flex h-8 items-center rounded-md border border-il-blue bg-il-blue px-3 text-xs font-semibold text-white hover:bg-il-blue"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function LoadingPanel({ sequence }: { sequence?: string[] | null }) {
  const genericSteps = [
    'Analyzing product intent...',
    'Drafting core narrative...',
  ]
  const templateSteps =
    sequence?.map((code) => `Generating ${PATTERN_FULL_LABEL[code] ?? code}...`) ?? []
  const loadingSteps = [
    ...genericSteps,
    ...templateSteps,
    'Polishing tone and readability...',
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
    <div className="flex flex-col items-center justify-center gap-3 py-3">
      <LoaderCircle className="h-10 w-10 animate-spin text-il-blue" aria-hidden="true" />
      <div className="text-center text-sm text-il-storm-60">
        <p className="mt-2 min-h-[1.5rem] transition-opacity duration-300">{loadingSteps[stepIndex]}</p>
      </div>
    </div>
  )
}

function MetricBadge(props: {
  short: string
  value: number | string | null | undefined
  title: string
  fullPrecision?: boolean
  strikeThrough?: boolean
}) {
  const content =
    props.value === null || props.value === undefined || props.value === ''
      ? 'NA'
      : typeof props.value === 'number'
        ? formatMetricNumber(props.value, props.fullPrecision ?? false)
        : props.value
  const highlightClass =
    props.short === 'BT'
      ? 'border-il-blue bg-blue-50 text-il-blue'
      : props.short === 'SD'
        ? 'border-il-altgeld bg-orange-50 text-il-altgeld'
        : 'border-il-storm-20 bg-white text-il-storm-60'
  return (
    <span
      className={`rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] ${highlightClass} ${props.strikeThrough ? 'line-through opacity-70' : ''}`}
      title={props.title}
    >
      {props.short}: {content}
    </span>
  )
}
