export type LengthOption = 'xs' | 's' | 'm' | 'l' | 'xl'
export type CategoryOption =
  | 'auto'
  | 'tech'
  | 'beauty'
  | 'health'
  | 'ecommerce'
  | 'finance'
  | 'home'
  | 'travel'
  | 'food'
  | 'education'
  | 'entertainment'
  | 'automotive'

export interface GenerateRequest {
  category: CategoryOption
  product_desc: string
  length: LengthOption
  generation_prompt: string | null
}

export interface StructuredSegment {
  label: string
  label_full: string
  text: string
}

export interface StructuredVariant {
  template_id: string
  template_name: string
  sequence: string[]
  segments: StructuredSegment[]
  output: string
}

export interface TemplateCandidate {
  template_id: string
  template_name: string
  sequence: string[]
  category_tags: string[]
  freq_score: number
}

export interface FindTemplatesResponse {
  category: string
  product_desc: string
  length: LengthOption
  templates: TemplateCandidate[]
}

export interface GenerateTemplateVariantRequest {
  template_id: string
  category: string
  product_desc: string
  length: LengthOption
  generation_prompt: string | null
}

export interface GenerateDirectResponse {
  output: string
}
