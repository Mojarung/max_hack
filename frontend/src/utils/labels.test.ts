import { describe, expect, it } from 'vitest'
import {
  eventKindMeta,
  issueCategoryIcon,
  ISSUE_STATUSES,
  ISSUE_STATUS_META,
  ISSUE_STATUS_TITLES,
  scoreColor,
} from './labels'

describe('подписи и значки', () => {
  it('фильтр заявок начинается с «Все» и знает все статусы', () => {
    expect(ISSUE_STATUSES[0]).toEqual({ value: null, title: 'Все' })
    expect(ISSUE_STATUSES.slice(1).map((s) => s.title)).toEqual(Object.values(ISSUE_STATUS_TITLES))
    // у каждого статуса есть цвет и значок
    for (const status of Object.keys(ISSUE_STATUS_TITLES)) {
      expect(ISSUE_STATUS_META[status as keyof typeof ISSUE_STATUS_META].icon).toMatch(/^mdi-/)
    }
  })

  it('значок категории заявки и запасной значок', () => {
    expect(issueCategoryIcon('elevator')).toBe('mdi-elevator-passenger')
    expect(issueCategoryIcon('неизвестно')).toBe('mdi-alert-circle-outline')
  })

  it('вид события и «Другое» для неизвестного', () => {
    expect(eventKindMeta('subbotnik').title).toBe('Субботник')
    expect(eventKindMeta('rave')).toMatchObject({ title: 'Другое', icon: 'mdi-calendar-star' })
  })

  it('цвет здоровья дома по шкале', () => {
    expect(scoreColor(90)).toBe('success')
    expect(scoreColor(75)).toBe('success')
    expect(scoreColor(60)).toBe('warning')
    expect(scoreColor(50)).toBe('warning')
    expect(scoreColor(49)).toBe('error')
  })
})
