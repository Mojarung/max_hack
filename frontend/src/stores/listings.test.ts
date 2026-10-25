import { describe, expect, it, vi } from 'vitest'
import { listingsApi } from '@/api/endpoints'
import { breakServer, useMockBackend } from '@/test/mockBackend'
import { resetAllStores } from './helpers'
import { useListingsStore } from './listings'

useMockBackend()

const ids = () =>
  useListingsStore()
    .items.map((l) => l.id)
    .sort()

describe('стор вещей соседей: список и фильтры', () => {
  it('показывает все открытые объявления', async () => {
    const store = useListingsStore()
    await store.load()
    expect(store.loaded).toBe(true)
    expect(store.loading).toBe(false)
    expect(ids()).toEqual([201, 202, 203, 204, 205, 206])
    expect(store.items.find((l) => l.id === 205)?.is_mine).toBe(true)
  })

  it('«Мои» оставляет только объявления жителя', async () => {
    const store = useListingsStore()
    store.scope = 'mine'
    await store.load()
    expect(ids()).toEqual([205])
  })

  it('«Даром», категория и поиск сужают список', async () => {
    const store = useListingsStore()
    store.freeOnly = true
    await store.load()
    expect(ids()).toEqual([201, 203, 206])

    store.freeOnly = false
    store.category = 'tools'
    await store.load()
    expect(store.items.map((l) => l.title)).toEqual(['Шуруповёрт Makita'])

    store.category = null
    store.query = 'коляска'
    await store.load()
    expect(ids()).toEqual([201])
  })

  it('ошибка сервера видна жителю', async () => {
    breakServer()
    const store = useListingsStore()
    await store.load()
    expect(store.error).toBe('Кузя споткнулся на сервере. Попробуйте ещё раз')
    expect(store.loaded).toBe(false)
  })

  it('старый ответ не затирает новый фильтр', async () => {
    const store = useListingsStore()
    store.scope = 'mine'
    const first = store.load()
    store.scope = 'active'
    const second = store.load()
    await Promise.all([first, second])
    expect(store.items).toHaveLength(6)
    expect(store.loading).toBe(false)
  })

  it('сброс при смене жителя очищает список', async () => {
    const store = useListingsStore()
    await store.load()
    resetAllStores()
    expect(store.items).toEqual([])
    expect(store.loaded).toBe(false)
  })
})

describe('стор вещей соседей: категории', () => {
  it('без ответа сервера берёт категории из контракта и спрашивает один раз', async () => {
    const spy = vi.spyOn(listingsApi, 'categories')
    const store = useListingsStore()
    await store.loadCategories()
    await store.loadCategories()
    expect(spy).toHaveBeenCalledTimes(1)
    expect(store.categories.find((c) => c.code === 'kids')?.title).toBe('Детское')
  })

  it('берёт категории сервера, если он их прислал', async () => {
    vi.spyOn(listingsApi, 'categories').mockResolvedValue(['books'])
    const store = useListingsStore()
    await store.loadCategories()
    expect(store.categories).toEqual([{ code: 'books', title: 'books' }])
  })

  it('при ошибке остаются категории по умолчанию', async () => {
    breakServer()
    const store = useListingsStore()
    const before = store.categories
    await store.loadCategories()
    expect(store.categories).toEqual(before)
  })
})

describe('стор вещей соседей: действия автора', () => {
  it('карточка объявления попадает в кэш', async () => {
    const store = useListingsStore()
    const data = await store.fetchDetail(202)
    expect(data.title).toBe('Диван-книжка')
    expect(store.details[202]?.price).toBe(3500)
  })

  it('закрытое объявление пропадает из открытых', async () => {
    const store = useListingsStore()
    await store.load()
    const data = await store.setStatus(205, 'closed')
    expect(data.status).toBe('closed')
    expect(ids()).not.toContain(205)
    expect(store.details[205]?.status).toBe('closed')
  })

  it('бронь оставляет объявление в списке', async () => {
    const store = useListingsStore()
    await store.load()
    await store.setStatus(205, 'reserved')
    expect(store.items.find((l) => l.id === 205)?.status).toBe('reserved')
  })

  it('удаление убирает объявление из списка и кэша', async () => {
    const store = useListingsStore()
    await store.load()
    await store.fetchDetail(205)
    await store.remove(205)
    expect(ids()).not.toContain(205)
    expect(store.details[205]).toBeUndefined()
  })
})
