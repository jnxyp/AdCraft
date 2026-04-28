import { useMutation } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { GenerateRequest, GenerateResponse } from '../types/generate'

async function createGeneration(payload: GenerateRequest): Promise<GenerateResponse> {
  const response = await apiClient.post<GenerateResponse>('/generate', payload)
  return response.data
}

export function useGenerate() {
  return useMutation({
    mutationFn: createGeneration,
  })
}
