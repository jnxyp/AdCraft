import { useMutation } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type {
  GenerateRequest,
  GenerateResponse,
  GenerateTemplateVariantRequest,
  StructuredVariant,
} from '../types/generate'

async function createGeneration(payload: GenerateRequest): Promise<GenerateResponse> {
  const response = await apiClient.post<GenerateResponse>('/generate', payload)
  return response.data
}

export function useGenerate() {
  return useMutation({
    mutationFn: createGeneration,
  })
}

async function createTemplateVariant(payload: GenerateTemplateVariantRequest): Promise<StructuredVariant> {
  const response = await apiClient.post<StructuredVariant>('/generate/template-variant', payload)
  return response.data
}

export function useGenerateTemplateVariant() {
  return useMutation({
    mutationFn: createTemplateVariant,
  })
}
