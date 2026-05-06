import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { apiClient } from '../api/client'
import type {
  EvalNextResponse,
  EvalSubmitRequest,
  EvalSubmitResponse,
  WinnerSlot,
} from '../types/eval'

const SESSION_KEY = 'ad_craft_eval_session_id'

function getSessionId(): string {
  const stored = window.localStorage.getItem(SESSION_KEY)
  if (stored) {
    return stored
  }
  const next = window.crypto.randomUUID()
  window.localStorage.setItem(SESSION_KEY, next)
  return next
}

async function fetchNextTask(
  sessionId: string,
  options?: { excludeTaskId?: string; randomize?: boolean },
): Promise<EvalNextResponse> {
  const response = await apiClient.get<EvalNextResponse>('/eval/next', {
    params: {
      session_id: sessionId,
      exclude_task_id: options?.excludeTaskId,
      randomize: options?.randomize ?? true,
    },
  })
  return response.data
}

async function submitFeedback(payload: EvalSubmitRequest): Promise<EvalSubmitResponse> {
  const response = await apiClient.post<EvalSubmitResponse>('/eval/submit', payload)
  return response.data
}

export function useEval() {
  const queryClient = useQueryClient()
  const sessionId = useMemo(() => getSessionId(), [])

  const nextTask = useQuery({
    queryKey: ['eval-next', sessionId],
    queryFn: () => fetchNextTask(sessionId, { randomize: true }),
  })

  const submit = useMutation({
    mutationFn: submitFeedback,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['eval-next', sessionId] })
    },
    onError: async (error) => {
      if (error instanceof AxiosError && error.response?.status === 409) {
        await queryClient.invalidateQueries({ queryKey: ['eval-next', sessionId] })
      }
    },
  })

  const vote = (winner: WinnerSlot) => {
    if (!nextTask.data?.task_id || nextTask.data.task_type !== 'pair') {
      return
    }
    submit.mutate({
      task_id: nextTask.data.task_id,
      task_type: 'pair',
      winner,
      session_id: sessionId,
    })
  }

  const shufflePair = async () => {
    const currentTaskId = nextTask.data?.task_id ?? undefined
    const next = await fetchNextTask(sessionId, { excludeTaskId: currentTaskId, randomize: true })
    queryClient.setQueryData(['eval-next', sessionId], next)
  }

  return {
    sessionId,
    nextTask,
    vote,
    shufflePair,
    isSubmitting: submit.isPending,
    submitError: submit.error,
  }
}
