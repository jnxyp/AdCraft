import { useMutation } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type {
  FindTemplatesResponse,
  GenerateDirectResponse,
  GenerateRequest,
  GenerateTemplateVariantRequest,
  StructuredVariant,
} from '../types/generate'

async function findTemplates(payload: GenerateRequest): Promise<FindTemplatesResponse> {
  const response = await apiClient.post<FindTemplatesResponse>('/generate/find-templates', payload)
  return response.data
}

export function useFindTemplates() {
  return useMutation({
    mutationFn: findTemplates,
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

async function createDirectOutput(payload: GenerateRequest): Promise<GenerateDirectResponse> {
  const response = await apiClient.post<GenerateDirectResponse>('/generate/direct', payload)
  return response.data
}

export function useGenerateDirect() {
  return useMutation({
    mutationFn: createDirectOutput,
  })
}
