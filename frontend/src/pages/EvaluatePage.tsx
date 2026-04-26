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
    <main className="h-screen overflow-hidden bg-il-storm-95 text-il-storm-10">
      <div className="mx-auto flex h-full w-full max-w-6xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <header className="shrink-0 rounded-lg border border-il-blue bg-il-blue px-5 py-5 text-white">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.14em] text-white/75">
                AdFrame
              </p>
              <h1 className="mt-1 text-3xl font-semibold leading-tight">
                Evaluate
              </h1>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="rounded border border-white/25 px-3 py-1 font-medium">
                {task?.category ?? 'Loading'}
              </span>
              <span className="rounded border border-white/20 px-3 py-1 text-white/85">
                {progress ? `Your evaluations: ${progress.session_done} / ${progress.total}` : 'Preparing'}
              </span>
              <span className="rounded border border-white/20 px-3 py-1 text-white/85">
                {progress ? `Globally resolved: ${progress.resolved} / ${progress.total}` : 'Resolving'}
              </span>
            </div>
          </div>
          <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/20">
            <div
              className="h-full rounded-full bg-il-orange transition-[width] duration-300"
              style={{ width: `${resolvedPercent}%` }}
            />
          </div>
        </header>

        <section className="min-h-0 flex-1 py-6">
          {nextTask.isPending ? <LoadingState /> : null}
          {nextTask.isError ? (
            <ErrorState onRetry={() => void nextTask.refetch()} />
          ) : null}
          {!nextTask.isPending && !nextTask.isError && task && !hasTask ? (
            <CompleteState onRefresh={() => void nextTask.refetch()} />
          ) : null}
          {hasTask && task ? (
            <div className="grid h-full min-h-0 grid-rows-[auto_1fr_auto] gap-5">
              {submitError ? <SubmitError /> : null}
              <div className="grid min-h-0 gap-5 lg:grid-cols-2">
                <EvalCard ad={task.ads[0]} label="A" />
                <EvalCard ad={task.ads[1]} label="B" />
              </div>
              <div className="shrink-0 grid gap-3 rounded-lg border border-il-storm-20 bg-white p-4 shadow-sm sm:grid-cols-3">
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
    </main>
  )
}

function LoadingState() {
  return (
    <div className="rounded-lg border border-il-storm-20 bg-white p-8 text-center">
      <RefreshCw className="mx-auto h-7 w-7 animate-spin text-il-blue" aria-hidden="true" />
      <p className="mt-4 font-medium text-il-storm-60">Loading next comparison</p>
    </div>
  )
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-lg border border-il-altgeld bg-white p-8 text-center">
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
  )
}

function CompleteState({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className="rounded-lg border border-il-storm-20 bg-white p-8 text-center">
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
  const base = 'min-h-12 rounded-md border px-4 py-3 text-base font-semibold transition disabled:cursor-not-allowed disabled:opacity-60'
  if (tone === 'primary') {
    return `${base} border-il-blue text-il-blue hover:border-il-orange hover:bg-il-orange hover:text-il-blue`
  }
  return `${base} border-il-storm-20 text-il-storm-10 hover:border-il-altgeld hover:text-il-altgeld`
}
