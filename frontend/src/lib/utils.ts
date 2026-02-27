import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Strip subject+class prefix from a skill tag and title-case the rest.
 * e.g. "hin_c2_matra_identify" → "Matra Identify"
 */
export function formatSkillTag(tag: string): string {
  return tag
    .replace(/^(mth|eng|sci|hin|comp|gk|moral|health)_c\d+_/, '')
    .replace(/_/g, ' ')
    .split(' ')
    .map((w, i) => {
      if (i === 0) return w.charAt(0).toUpperCase() + w.slice(1)
      if (['and', 'or', 'of', 'in', 'the', 'a'].includes(w)) return w
      return w.charAt(0).toUpperCase() + w.slice(1)
    })
    .join(' ')
}
