export type WinnerSlot = 'a' | 'b' | 'tie'

export interface EvalAd {
  slot: string
  ad_id: string
  body: string
  sequence: string[]
  seq_len: number
  length_bucket: 'xs' | 's' | 'm' | 'l' | 'xl'
  cluster_id: string | null
}

export interface EvalProgress {
  session_done: number
  responses: number
  resolved: number
  total: number
  resolved_generated: number
  total_generated: number
}

export interface EvalNextResponse {
  task_id: string | null
  task_type: string | null
  category: string | null
  pair_scope: string | null
  cluster_id: string | null
  progress: EvalProgress
  ads: EvalAd[]
}

export interface EvalSubmitRequest {
  task_id: string
  task_type: 'pair'
  winner: WinnerSlot
  session_id: string
}

export interface EvalSubmitResponse {
  accepted: boolean
  task_status: 'pending' | 'resolved'
  vote_count: number
  vote_summary: Record<WinnerSlot, number>
  resolved_winner: WinnerSlot | null
}
