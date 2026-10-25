import { describe, expect, it } from 'vitest'
import { cn } from './utils'

describe('склейка классов', () => {
  it('убирает пустые классы, из спорных классов Tailwind оставляет последний', () => {
    expect(cn('px-2 py-1', false && 'hidden', null, 'px-4')).toBe('py-1 px-4')
    expect(cn('text-sm', { 'font-bold': true, italic: false })).toBe('text-sm font-bold')
  })
})
