import { describe, expect, it } from 'vitest'
import {
  boldSegments,
  formatCountdown,
  formatDistance,
  formatHours,
  formatPrice,
  formatWalk,
  plural,
} from './format'

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

describe('formatWalk', () => {
  it('shows minutes and distance', () => {
    expect(formatWalk(540, 7 * 60 + 10)).toBe('≈ 7 мин пешком · 540 м')
  })

  it('rounds short walks up to a minute and long ones to hours', () => {
    expect(formatWalk(30, 20)).toBe('≈ 1 мин пешком · 30 м')
    expect(formatWalk(5200, 70 * 60)).toBe('≈ 1 ч 10 мин пешком · 5,2 км')
    expect(formatWalk(4800, 60 * 60)).toBe('≈ 1 ч пешком · 4,8 км')
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

describe('orgTitle', () => {
  it('раскрывает сокращения', async () => {
    const { orgTitle, orgTitleCap } = await import('./format')
    expect(orgTitle('УК «Уютный дом»')).toBe('управляющая компания «Уютный дом»')
    expect(orgTitle('Регоператор ТКО «Гринта»')).toBe('оператор вывоза мусора «Гринта»')
    expect(orgTitle('Региональный оператор по обращению с ТКО (демо)')).toBe(
      'оператор вывоза мусора (демо)',
    )
    expect(orgTitleCap('УК «Уютный дом»')).toBe('Управляющая компания «Уютный дом»')
    expect(orgTitle(null)).toBe('')
  })

  it('ставит название в нужный падеж', async () => {
    const { orgAccusative, orgRecipient } = await import('./format')
    expect(orgAccusative('УК «Уютный дом»')).toBe('управляющую компанию «Уютный дом»')
    expect(orgRecipient('УК «Уютный дом»')).toBe('в управляющую компанию «Уютный дом»')
    expect(orgRecipient('Регоператор ТКО «Гринта»')).toBe('оператору вывоза мусора «Гринта»')
    expect(orgAccusative('Регоператор ТКО «Гринта»')).toBe('оператора вывоза мусора «Гринта»')
    expect(orgRecipient('ГЖИ')).toBe('в Госжилинспекцию')
    expect(orgRecipient('ООО «Сервис»')).toBe('в организацию ООО «Сервис»')
    expect(orgRecipient(null)).toBe('')
  })

  it('раскрывает сокращения внутри текста', async () => {
    const { plainOrgWords, capitalize } = await import('./format')
    expect(capitalize(plainOrgWords('УК: бригада на месте'))).toBe(
      'Управляющая компания: бригада на месте',
    )
    expect(plainOrgWords('Обращение отправлено: Регоператор ТКО «Гринта»')).toBe(
      'Обращение отправлено: оператор вывоза мусора «Гринта»',
    )
    expect(plainOrgWords('ЖУКОВ и УКРОП')).toBe('ЖУКОВ и УКРОП')
  })
})

describe('boldSegments', () => {
  it('splits bot markdown into plain and bold parts', () => {
    expect(boldSegments('Заявка **Течёт крыша** набрала голоса')).toEqual([
      { text: 'Заявка ', bold: false },
      { text: 'Течёт крыша', bold: true },
      { text: ' набрала голоса', bold: false },
    ])
  })

  it('keeps unpaired asterisks and plain text as is', () => {
    expect(boldSegments('5 ** 2')).toEqual([{ text: '5 ** 2', bold: false }])
    expect(boldSegments('')).toEqual([])
  })
})
