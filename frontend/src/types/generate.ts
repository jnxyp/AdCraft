export type LengthOption = 'xs' | 's' | 'm' | 'l' | 'xl'

export interface GenerateRequest {
  category: string
  product_desc: string
  length: LengthOption
  generation_prompt: string | null
}

export interface StructuredVariant {
  template_id: string
  template_name: string
  sequence: string[]
  output: string
}

export interface GenerateResponse {
  generation_id: string
  category: string
  product_desc: string
  structured_variants: StructuredVariant[]
  direct_output: string
}
