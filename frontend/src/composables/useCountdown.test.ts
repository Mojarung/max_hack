import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { useCountdown } from './useCountdown'

const NOW = new Date('2026-10-21T10:00:00+04:00').getTime()
const HOUR = 3_600_000

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('таймер срока заявки', () => {
  it('показывает остаток и обновляется раз в полминуты', () => {
    const scope = effectScope()
    const deadline = ref<string | null>(new Date(NOW + 2 * HOUR + 30_000).toISOString())
    const countdown = scope.run(() => useCountdown(deadline))!
    expect(countdown.value).toEqual({ overdue: false, urgent: true, text: '2 ч' })

    vi.advanceTimersByTime(30_000)
    expect(countdown.value?.text).toBe('2 ч')
    // прошло 2 ч 1,5 мин: срок вышел минуту назад
    vi.advanceTimersByTime(2 * HOUR + 60_000)
    expect(countdown.value?.text).toBe('просрочено на 1 мин')
    expect(countdown.value?.overdue).toBe(true)
    scope.stop()
  })

  it('без срока и с неверной датой таймера нет', () => {
    const scope = effectScope()
    const deadline = ref<string | null>(null)
    const countdown = scope.run(() => useCountdown(deadline))!
    expect(countdown.value).toBeNull()
    deadline.value = 'не дата'
    expect(countdown.value).toBeNull()
    deadline.value = new Date(NOW + 5 * HOUR).toISOString()
    expect(countdown.value?.text).toBe('5 ч')
    scope.stop()
  })

  it('часы общие на всех и останавливаются, когда таймеров не осталось', () => {
    const first = effectScope()
    const second = effectScope()
    const deadline = ref(new Date(NOW + HOUR).toISOString())
    first.run(() => useCountdown(deadline))
    second.run(() => useCountdown(deadline))
    expect(vi.getTimerCount()).toBe(1)
    first.stop()
    expect(vi.getTimerCount()).toBe(1)
    second.stop()
    expect(vi.getTimerCount()).toBe(0)
  })
})
