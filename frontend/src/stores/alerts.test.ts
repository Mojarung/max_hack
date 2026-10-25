import { describe, expect, it, vi } from 'vitest'
import { safetyApi } from '@/api/endpoints'
import { notify } from '@/lib/notify'
import { breakServer, fakeMax, flushMock, setScenario, useMockBackend } from '@/test/mockBackend'
import { useAlertsStore } from './alerts'
import { useSessionStore } from './session'

useMockBackend()

describe('стор тревоги', () => {
  it('без тревоги ничего не показывает', async () => {
    const store = useAlertsStore()
    await store.check()
    expect(store.active).toBeNull()
  })

  it('тревога открывается на весь экран, телефон вибрирует, Кузя ищет укрытие', async () => {
    setScenario({ name: 'alert' })
    const max = fakeMax()
    const store = useAlertsStore()
    await store.check()
    expect(store.active?.kind_title).toBe('Беспилотная опасность')
    expect(store.minimized).toBe(false)
    expect(max.notify).toHaveBeenCalledWith('warning')
    await flushMock()
    expect(store.nearestLoading).toBe(false)
    expect(store.nearest?.id).toBe(1)
    // без GPS берём координаты по умолчанию
    expect(store.position?.source).toBe('house')
  })

  it('укрытие ищет от координат дома жителя', async () => {
    setScenario({ name: 'alert' })
    fakeMax()
    await useSessionStore().init()
    const store = useAlertsStore()
    await store.check()
    await flushMock()
    expect(store.position).toEqual({ lat: 54.3857, lon: 48.6072, source: 'house' })
  })

  it('повторная проверка той же тревоги не вибрирует снова', async () => {
    setScenario({ name: 'alert' })
    const max = fakeMax()
    const store = useAlertsStore()
    await store.check()
    store.minimized = true
    await store.check()
    expect(max.notify).toHaveBeenCalledTimes(1)
    expect(store.minimized).toBe(true)
  })

  it('учебная тревога и отбой с сообщением жителю', async () => {
    const success = vi.spyOn(notify, 'success')
    const store = useAlertsStore()
    await store.startTest()
    expect(store.active?.message).toBe('Учебная тревога. Это проверка оповещения жителей.')
    await store.end()
    expect(store.active).toBeNull()
    expect(success).toHaveBeenCalledWith(
      'Отбой тревоги',
      'Опасность миновала. Можно возвращаться домой',
    )
  })

  it('когда тревога закончилась на сервере, оверлей закрывается без сообщения', async () => {
    const success = vi.spyOn(notify, 'success')
    const store = useAlertsStore()
    await store.startTest()
    vi.spyOn(safetyApi, 'activeAlert').mockResolvedValue(null)
    await store.check()
    expect(store.active).toBeNull()
    expect(success).not.toHaveBeenCalled()
  })

  it('отбой без тревоги ничего не отправляет', async () => {
    const spy = vi.spyOn(safetyApi, 'endAlert')
    await useAlertsStore().end()
    expect(spy).not.toHaveBeenCalled()
  })

  it('ошибка сети при проверке не мешает запуску', async () => {
    breakServer()
    const store = useAlertsStore()
    await expect(store.check()).resolves.toBeUndefined()
    expect(store.active).toBeNull()
  })

  it('если укрытия не нашлись, ближайшего нет', async () => {
    breakServer()
    const store = useAlertsStore()
    await store.findNearest()
    expect(store.nearest).toBeNull()
    expect(store.nearestLoading).toBe(false)
  })
})
