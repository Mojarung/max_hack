import { describe, expect, it } from 'vitest'
import { breakServer, setScenario, useMockBackend } from '@/test/mockBackend'
import { useAnnouncementsStore } from './announcements'
import { resetAllStores } from './helpers'

useMockBackend()

describe('стор объявлений дома', () => {
  it('закреплённое объявление сверху, на главной два первых', async () => {
    const store = useAnnouncementsStore()
    await store.load()
    expect(store.loaded).toBe(true)
    expect(store.items.map((a) => a.id)).toEqual([901, 902])
    expect(store.top.map((a) => a.title)).toEqual([
      'Отключение горячей воды 1-3 октября',
      'Покраска подъезда 2',
    ])
  })

  it('житель не может закрепить своё объявление: оно встаёт после закреплённых', async () => {
    const store = useAnnouncementsStore()
    await store.load()
    await store.create({ title: 'Нашлись ключи', text: 'У лифта', pin: true })
    expect(store.items.map((a) => a.title)).toEqual([
      'Отключение горячей воды 1-3 октября',
      'Нашлись ключи',
      'Покраска подъезда 2',
    ])
    expect(store.items[1]?.pinned).toBe(false)
    expect(store.items[1]?.is_mine).toBe(true)
  })

  it('администратор закрепляет новое объявление первым', async () => {
    setScenario({ role: 'admin' })
    const store = useAnnouncementsStore()
    await store.load()
    await store.create({ title: 'Собрание в четверг', text: '', pin: true })
    expect(store.items[0]?.title).toBe('Собрание в четверг')
    expect(store.items[0]?.pinned).toBe(true)
  })

  it('закрепление и удаление меняют порядок', async () => {
    const store = useAnnouncementsStore()
    await store.load()
    await store.setPinned(901, false)
    expect(store.items.every((a) => !a.pinned)).toBe(true)
    await store.setPinned(902, true)
    expect(store.items[0]?.id).toBe(902)
    await store.remove(902)
    expect(store.items.map((a) => a.id)).toEqual([901])
  })

  it('ошибка сервера видна жителю', async () => {
    breakServer()
    const store = useAnnouncementsStore()
    await store.load()
    expect(store.error).toBe('Кузя споткнулся на сервере. Попробуйте ещё раз')
    expect(store.loading).toBe(false)
  })

  it('сброс при смене жителя очищает список', async () => {
    const store = useAnnouncementsStore()
    await store.load()
    resetAllStores()
    expect(store.items).toEqual([])
    expect(store.loaded).toBe(false)
  })
})
