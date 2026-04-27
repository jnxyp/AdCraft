import { AlertCircle, CheckCircle2, RefreshCw } from 'lucide-react'
import { EvalCard } from '../components/EvalCard'
import { useEval } from '../hooks/useEval'
import type { WinnerSlot } from '../types/eval'

const ACTIONS: Array<{ winner: WinnerSlot; label: string; tone: 'primary' | 'neutral' }> = [
  { winner: 'a', label: 'A is better', tone: 'primary' },
  { winner: 'tie', label: 'About the same', tone: 'neutral' },
  { winner: 'b', label: 'B is better', tone: 'primary' },
]

export function EvaluatePage() {
  const { nextTask, vote, isSubmitting, submitError } = useEval()
  const task = nextTask.data
  const progress = task?.progress
  const resolvedPercent = progress && progress.total > 0
    ? Math.min(100, Math.round((progress.resolved / progress.total) * 100))
    : 0
  const hasTask = Boolean(task?.task_id && task.ads.length >= 2)

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] pt-5">
        <header className="shrink-0 rounded-lg border border-il-blue bg-il-blue px-5 py-5 text-white">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.14em] text-white/75">
                Human Feedback
              </p>
              <h1 className="mt-1 text-3xl font-semibold leading-tight">
                Evaluate
              </h1>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="rounded border border-white/20 px-3 py-1 text-white/85">
                {progress ? `Your evaluations: ${progress.session_done}` : 'Preparing'}
              </span>
            </div>
          </div>
          <div className="mt-5 flex items-center justify-between gap-4 text-sm text-white/80">
            <span>{progress ? `Globally resolved: ${progress.resolved} / ${progress.total}` : 'Globally resolved'}</span>
            <span>{resolvedPercent}%</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/20">
            <div
              className="h-full rounded-full bg-il-orange transition-[width] duration-300"
              style={{ width: `${resolvedPercent}%` }}
            />
          </div>
        </header>

        <section className="min-h-0 pt-5">
          {nextTask.isPending ? <LoadingState /> : null}
          {nextTask.isError ? (
            <ErrorState onRetry={() => void nextTask.refetch()} />
          ) : null}
          {!nextTask.isPending && !nextTask.isError && task && !hasTask ? (
            <CompleteState onRefresh={() => void nextTask.refetch()} />
          ) : null}
          {hasTask && task ? (
            <div className="relative grid h-full min-h-0 grid-rows-[minmax(0,1fr)_96px] gap-5">
              {submitError ? (
                <div className="absolute left-0 right-0 top-0 z-10">
                  <SubmitError />
                </div>
              ) : null}
              <div className="grid min-h-0 gap-5 lg:grid-cols-2">
                <EvalCard ad={task.ads[0]} label="A" />
                <EvalCard ad={task.ads[1]} label="B" />
              </div>
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
            </div>
          ) : null}
        </section>
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
          className="mt-5 rounded-md border border-il-blue px-4 py-2 font-semibold text-il-blue hover:border-il-orange hover:text-il-altgeld"
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
          className="mt-6 rounded-md bg-il-blue px-4 py-2 font-semibold text-white hover:bg-il-orange hover:text-il-blue"
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

function buttonClass(tone: 'primary' | 'neutral') {
  const base = 'h-16 rounded-md border px-4 text-base font-semibold transition disabled:cursor-not-allowed disabled:opacity-60'
  if (tone === 'primary') {
    return `${base} border-il-blue text-il-blue hover:border-il-orange hover:bg-il-orange hover:text-il-blue`
  }
  return `${base} border-il-storm-20 text-il-storm-10 hover:border-il-altgeld hover:text-il-altgeld`
}
