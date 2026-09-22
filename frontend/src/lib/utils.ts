import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Склейка классов в стиле shadcn-vue. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
