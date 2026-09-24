import { describe, expect, it } from 'vitest'
import { formatCountdown, formatDistance, formatHours, formatPrice, plural } from './format'

const MIN = 60_000
const HOUR = 60 * MIN
const DAY = 24 * HOUR

describe('formatCountdown', () => {
  it('shows minutes when less than an hour is left', () => {
    expect(formatCountdown(45 * MIN)).toEqual({ overdue: false, urgent: true, text: '45 мин' })
  })

  it('shows hours and minutes', () => {
    expect(formatCountdown(3 * HOUR + 15 * MIN).text).toBe('3 ч 15 мин')
  })

  it('drops zero minutes', () => {
    expect(formatCountdown(5 * HOUR).text).toBe('5 ч')
  })

  it('shows days and hours for long deadlines', () => {
    const result = formatCountdown(2 * DAY + 5 * HOUR + 10 * MIN)
    expect(result.text).toBe('2 д 5 ч')
    expect(result.urgent).toBe(false)
  })

  it('marks negative values as overdue', () => {
    expect(formatCountdown(-(5 * HOUR))).toEqual({
      overdue: true,
      urgent: false,
      text: 'просрочено на 5 ч',
    })
  })

  it('handles less than a minute', () => {
    expect(formatCountdown(20_000).text).toBe('меньше минуты')
  })
})

describe('plural', () => {
  const forms: [string, string, string] = ['голос', 'голоса', 'голосов']
  it.each([
    [1, 'голос'],
    [2, 'голоса'],
    [5, 'голосов'],
    [11, 'голосов'],
    [21, 'голос'],
    [22, 'голоса'],
    [112, 'голосов'],
  ])('%i -> %s', (n, expected) => {
    expect(plural(n, forms)).toBe(expected)
  })
})

describe('formatDistance and formatPrice', () => {
  it('formats meters and kilometers', () => {
    expect(formatDistance(420)).toBe('420 м')
    expect(formatDistance(1234)).toBe('1,2 км')
    expect(formatDistance(null)).toBe('')
  })

  it('shows "Даром" for free listings', () => {
    expect(formatPrice(0, true)).toBe('Даром')
    expect(formatPrice(1500, false)).toMatch(/^1\s500 ₽$/)
  })
})

describe('formatHours', () => {
  it('до двух суток - часами, дальше - днями', () => {
    expect(formatHours(24)).toBe('24\u00a0часа')
    expect(formatHours(1)).toBe('1\u00a0час')
    expect(formatHours(168)).toBe('7\u00a0дней')
    expect(formatHours(720)).toBe('30\u00a0дней')
  })
})
