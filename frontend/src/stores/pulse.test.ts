import { describe, expect, it, vi } from 'vitest'
import { meApi } from '@/api/endpoints'
import type { PulseOut } from '@/api/types'
import { breakServer, setScenario, useMockBackend } from '@/test/mockBackend'
import { resetAllStores } from './helpers'
import { usePulseStore } from './pulse'

useMockBackend()

describe('стор пульса дома', () => {
  it('одна просроченная заявка: Кузя волнуется и ждёт голоса жителя', async () => {
    const store = usePulseStore()
    await store.load()
    expect(store.loading).toBe(false)
    expect(store.pulse?.mood).toBe('worried')
    expect(store.pulse?.stats.overdue_issues).toBe(1)
    expect(store.pulse?.stats.awaiting_my_vote).toBe(1)
    expect(store.pulse?.phrase).toContain('срок вышел')
  })

  it('в пустом доме Кузя доволен и предлагает субботник', async () => {
    setScenario({ name: 'empty' })
    const store = usePulseStore()
    await store.load()
    expect(store.pulse?.mood).toBe('happy')
    expect(store.pulse?.phrase).toBe('В доме тишь да гладь. Может, устроим субботник?')
  })

  it('во время тревоги Кузя бьёт тревогу', async () => {
    setScenario({ name: 'alert' })
    const store = usePulseStore()
    await store.load()
    expect(store.pulse?.mood).toBe('alarm')
    expect(store.pulse?.stats.active_alert).toBe(true)
  })

  it('ошибка сервера видна жителю', async () => {
    breakServer()
    const store = usePulseStore()
    await store.load()
    expect(store.error).toBe('Кузя споткнулся на сервере. Попробуйте ещё раз')
    expect(store.pulse).toBeNull()
  })

  it('тихое обновление ничего не делает, пока пульс не загружен', () => {
    const spy = vi.spyOn(meApi, 'pulse')
    usePulseStore().softRefresh()
    expect(spy).not.toHaveBeenCalled()
  })

  it('частые тихие обновления сливаются в один запрос', async () => {
    const store = usePulseStore()
    await store.load()
    const fresh = { ...store.pulse!, score: 99 } as PulseOut
    const spy = vi.spyOn(meApi, 'pulse').mockResolvedValue(fresh)
    vi.useFakeTimers()
    store.softRefresh()
    store.softRefresh()
    store.softRefresh()
    await vi.advanceTimersByTimeAsync(400)
    vi.useRealTimers()
    expect(spy).toHaveBeenCalledTimes(1)
    expect(store.pulse?.score).toBe(99)
  })

  it('сброс при смене жителя забывает пульс', async () => {
    const store = usePulseStore()
    await store.load()
    resetAllStores()
    expect(store.pulse).toBeNull()
  })
})
