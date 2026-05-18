import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, RefreshCw } from 'lucide-react'
import { EvalCard } from '../components/EvalCard'
import { useEval } from '../hooks/useEval'
import type { WinnerSlot } from '../types/eval'

const ACTIONS: Array<{ winner: WinnerSlot; label: string; tone: 'primary' | 'neutral' }> = [
  { winner: 'a', label: 'A is better', tone: 'primary' },
  { winner: 'tie', label: 'About the same', tone: 'neutral' },
  { winner: 'b', label: 'B is better', tone: 'primary' },
]

export function EvaluatePage({ showDetails }: { showDetails: boolean }) {
  const [includeRanking, setIncludeRanking] = useState(true)
  const [includeGenerated, setIncludeGenerated] = useState(true)

  const scopes = useMemo(() => [
    ...(includeRanking ? ['same_cluster', 'cross_cluster'] : []),
    ...(includeGenerated ? ['template_vs_direct'] : []),
  ], [includeRanking, includeGenerated])

  const toggleRanking = () => setIncludeRanking(v => !v)
  const toggleGenerated = () => setIncludeGenerated(v => !v)

  const { nextTask, vote, shufflePair, isSubmitting, submitError } = useEval(scopes)
  const task = nextTask.data
  const progress = task?.progress
  const [sessionPlusOneVisible, setSessionPlusOneVisible] = useState(false)
  const [globalPlusOneVisible, setGlobalPlusOneVisible] = useState(false)
  const prevSessionDoneRef = useRef<number | null>(null)
  const prevResponsesRef = useRef<number | null>(null)
  const resolvedPercent = progress && progress.total > 0
    ? Math.min(100, Math.round((progress.resolved / progress.total) * 100))
    : 0
  const resolvedOriginal = progress ? progress.resolved - (progress.resolved_generated ?? 0) : 0
  const totalOriginal = progress ? progress.total - (progress.total_generated ?? 0) : 0
  const hasTask = Boolean(task?.task_id && task.ads.length >= 2)

  useEffect(() => {
    const current = progress?.session_done
    if (typeof current !== 'number') {
      return
    }
    const prev = prevSessionDoneRef.current
    if (prev !== null && current > prev) {
      setSessionPlusOneVisible(false)
      const raf = window.requestAnimationFrame(() => setSessionPlusOneVisible(true))
      const timer = window.setTimeout(() => setSessionPlusOneVisible(false), 1100)
      prevSessionDoneRef.current = current
      return () => {
        window.cancelAnimationFrame(raf)
        window.clearTimeout(timer)
      }
    }
    prevSessionDoneRef.current = current
  }, [progress?.session_done])

  useEffect(() => {
    const current = progress?.responses
    if (typeof current !== 'number') {
      return
    }
    const prev = prevResponsesRef.current
    if (prev !== null && current > prev) {
      setGlobalPlusOneVisible(false)
      const raf = window.requestAnimationFrame(() => setGlobalPlusOneVisible(true))
      const timer = window.setTimeout(() => setGlobalPlusOneVisible(false), 1100)
      prevResponsesRef.current = current
      return () => {
        window.cancelAnimationFrame(raf)
        window.clearTimeout(timer)
      }
    }
    prevResponsesRef.current = current
  }, [progress?.responses])

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-[10px]">
        <header className="shrink-0 rounded-lg border border-il-blue bg-il-blue px-5 py-5 text-white">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <h1 className="text-4xl font-bold tracking-[0.04em]">Global Evaluation Progress</h1>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <ContributionBadge
                label="Your Contributions"
                value={progress?.session_done}
                plusOneVisible={sessionPlusOneVisible}
              />
              <ContributionBadge
                label="Global Contributions"
                value={progress?.responses}
                plusOneVisible={globalPlusOneVisible}
              />
            </div>
          </div>
          <div className="mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 text-sm text-white/80">
            <span className="font-semibold">Globally resolved</span>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded border border-white/20 px-2 py-0.5 text-xs font-semibold">
                Ad Template Ranking: {progress ? `${resolvedOriginal} / ${totalOriginal}` : '—'}
              </span>
              <span className="rounded border border-white/20 px-2 py-0.5 text-xs font-semibold">
                Structured vs. Direct: {progress ? `${progress.resolved_generated} / ${progress.total_generated}` : '—'}
              </span>
              <span>{resolvedPercent}%</span>
            </div>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/20">
            <div
              className="h-full rounded-full bg-il-orange transition-[width] duration-300"
              style={{ width: `${resolvedPercent}%` }}
            />
          </div>
        </header>

        <section className="min-h-0">
          {nextTask.isPending ? <LoadingState /> : null}
          {nextTask.isError ? (
            <ErrorState onRetry={() => void nextTask.refetch()} />
          ) : null}
          {!nextTask.isPending && !nextTask.isError ? (
            <div className="relative flex h-full min-h-0 flex-col gap-[10px]">
              {submitError ? (
                <div className="absolute left-0 right-0 top-0 z-10">
                  <SubmitError />
                </div>
              ) : null}
              <div className="flex min-h-0 flex-1 flex-col gap-[10px] rounded-lg border border-il-storm-20 bg-il-storm-95/40 p-3">
                <div className="flex items-center justify-between gap-3 rounded-md border border-il-storm-20 bg-white px-3 py-2">
                  <div className="min-w-0 flex items-center gap-2">
                    <p className="text-sm font-semibold uppercase tracking-[0.12em] text-il-blue">Pair Evaluation</p>
                    {showDetails && task ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded border border-il-storm-20 bg-white px-2 py-0.5 text-xs font-semibold text-il-storm-60">
                          Task ID: {task.task_id}
                        </span>
                        <span className="rounded border border-il-storm-20 bg-white px-2 py-0.5 text-xs font-semibold text-il-storm-60">
                          Task Type: pair
                        </span>
                        <span className="rounded border border-il-storm-20 bg-white px-2 py-0.5 text-xs font-semibold text-il-storm-60">
                          Task Scope: {task.pair_scope === 'cross_cluster' ? 'Cross Cluster' : task.pair_scope === 'template_vs_direct' ? 'Structured vs. Direct' : 'Same Cluster'}
                        </span>
                      </div>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <ScopeToggle
                      label="Ad Template Ranking"
                      active={includeRanking}
                      onToggle={toggleRanking}
                    />
                    <ScopeToggle
                      label="Structured vs. Direct"
                      active={includeGenerated}
                      onToggle={toggleGenerated}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        void shufflePair()
                      }}
                      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-il-storm-20 bg-white px-3 text-xs font-semibold text-il-storm-60 transition hover:border-il-blue hover:text-il-blue"
                    >
                      <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                      Switch Pair
                    </button>
                  </div>
                </div>
                {scopes.length === 0 ? (
                  <NoScopeState />
                ) : !hasTask ? (
                  <CompleteState onRefresh={() => void nextTask.refetch()} />
                ) : task ? (
                  <div className="grid min-h-0 gap-[10px] lg:grid-cols-2">
                    <EvalCard
                      ad={task.ads[0]}
                      label="A"
                      category={task.category}
                      showDetails={showDetails}
                    />
                    <EvalCard
                      ad={task.ads[1]}
                      label="B"
                      category={task.category}
                      showDetails={showDetails}
                    />
                  </div>
                ) : null}
              </div>
              {hasTask && task ? (
                <div className="grid h-24 shrink-0 items-center gap-3 rounded-lg border border-il-storm-20 bg-white p-4 shadow-sm sm:grid-cols-3">
                  {ACTIONS.map((action) => (
                    <button
                      key={action.winner}
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => vote(action.winner)}
                      className={buttonClass(action.tone)}
                    >
                      {isSubmitting ? 'Submitting...' : action.label}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>
  )
}

function ContributionBadge({
  label,
  value,
  plusOneVisible,
}: {
  label: string
  value: number | undefined
  plusOneVisible: boolean
}) {
  return (
    <div className="relative flex items-center justify-end">
      <span className="rounded border border-white/20 px-3 py-1 text-base font-semibold text-white">
        {typeof value === 'number' ? `${label}: ${value}` : 'Preparing'}
      </span>
      {plusOneVisible ? (
        <span className="plus-one-float pointer-events-none absolute -top-5 right-2 text-sm font-bold text-il-orange">
          +1
        </span>
      ) : null}
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex h-full items-center justify-center rounded-lg border border-il-storm-20 bg-white p-8 text-center">
      <div>
        <RefreshCw className="mx-auto h-7 w-7 animate-spin text-il-blue" aria-hidden="true" />
        <p className="mt-4 font-medium text-il-storm-60">Loading next comparison</p>
      </div>
    </div>
  )
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex h-full items-center justify-center rounded-lg border border-il-altgeld bg-white p-8 text-center">
      <div>
        <AlertCircle className="mx-auto h-7 w-7 text-il-altgeld" aria-hidden="true" />
        <p className="mt-4 font-semibold text-il-storm-10">Could not load a task.</p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 rounded-md border border-il-blue bg-white px-4 py-2 font-semibold text-il-blue transition hover:bg-il-blue hover:text-white active:bg-il-blue active:text-white"
        >
          Try again
        </button>
      </div>
    </div>
  )
}

function CompleteState({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className="flex h-full items-center justify-center rounded-lg border border-il-storm-20 bg-white p-8 text-center">
      <div>
        <CheckCircle2 className="mx-auto h-8 w-8 text-il-blue" aria-hidden="true" />
        <h2 className="mt-4 text-2xl font-semibold text-il-blue">All done! Thank you.</h2>
        <button
          type="button"
          onClick={onRefresh}
          className="mt-6 rounded-md border-2 border-il-blue bg-white px-4 py-2 font-bold text-il-blue transition hover:bg-il-blue hover:text-white active:bg-il-blue active:text-white"
        >
          Refresh
        </button>
      </div>
    </div>
  )
}

function SubmitError() {
  return (
    <div className="rounded-lg border border-il-altgeld bg-white px-4 py-3 text-sm font-medium text-il-altgeld">
      This response was not saved. Please try again.
    </div>
  )
}

function NoScopeState() {
  return (
    <div className="flex flex-1 items-center justify-center rounded-lg border border-il-storm-20 bg-white p-8 text-center">
      <p className="text-sm font-medium text-il-storm-40">Please select at least one task type above.</p>
    </div>
  )
}

function ScopeToggle({
  label,
  active,
  onToggle,
}: {
  label: string
  active: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={[
        'inline-flex h-8 items-center rounded-md border px-3 text-xs font-semibold transition',
        active
          ? 'border-il-blue bg-white text-il-blue'
          : 'border-il-storm-20 bg-white text-il-storm-40',
      ].join(' ')}
    >
      <span
        className={[
          'mr-1.5 inline-block h-2 w-2 rounded-full',
          active ? 'bg-il-blue' : 'bg-il-storm-40',
        ].join(' ')}
        aria-hidden="true"
      />
      {label}
    </button>
  )
}

function buttonClass(tone: 'primary' | 'neutral') {
  const base = 'h-16 rounded-md border px-4 text-base font-semibold transition disabled:cursor-not-allowed disabled:opacity-60'
  if (tone === 'primary') {
    return `${base} border-il-blue bg-white text-il-blue hover:bg-il-blue hover:text-white active:bg-il-blue active:text-white`
  }
  return `${base} border-il-orange bg-white text-il-orange hover:bg-il-orange hover:text-white active:bg-il-orange active:text-white`
}
