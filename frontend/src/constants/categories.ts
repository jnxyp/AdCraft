import type { CategoryOption } from '../types/generate'

export const CATEGORIES: CategoryOption[] = [
  'auto',
  'tech',
  'beauty',
  'health',
  'ecommerce',
  'finance',
  'home',
  'travel',
  'food',
  'education',
  'entertainment',
  'automotive',
]

const CATEGORY_DISPLAY_NAMES: Record<CategoryOption, string> = {
  auto: 'Auto Detect',
  tech: 'Technology',
  beauty: 'Beauty',
  health: 'Health',
  ecommerce: 'Ecommerce',
  finance: 'Finance',
  home: 'Home',
  travel: 'Travel',
  food: 'Food',
  education: 'Education',
  entertainment: 'Entertainment',
  automotive: 'Automotive',
}

export function getCategoryDisplayName(category: string): string {
  if (category in CATEGORY_DISPLAY_NAMES) {
    return CATEGORY_DISPLAY_NAMES[category as CategoryOption]
  }
  return category
}
