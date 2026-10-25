import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/client'
import { breakServer, useMockBackend } from '@/test/mockBackend'
import { resetAllStores } from './helpers'
import { useIssuesStore } from './issues'

useMockBackend()

const byId = (id: number) => useIssuesStore().items.find((i) => i.id === id)

describe('стор заявок: список', () => {
  it('загружает заявки дома, свежие сверху', async () => {
    const store = useIssuesStore()
    await store.load()
    expect(store.loaded).toBe(true)
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
    expect(store.items).toHaveLength(7)
    expect(store.items[0]?.title).toBe('Течёт крыша над 9 этажом')
  })

  it('фильтрует по статусу и по словам из поиска', async () => {
    const store = useIssuesStore()
    store.status = 'voting'
    await store.load()
    expect(store.items.map((i) => i.id).sort()).toEqual([101, 102])

    store.status = null
    store.query = '  лифт '
    await store.load()
    expect(store.items.map((i) => i.title)).toEqual(['Не работает лифт в подъезде 1'])
  })

  it('показывает понятную ошибку, если сервер упал', async () => {
    breakServer()
    const store = useIssuesStore()
    await store.load()
    expect(store.error).toBe('Кузя споткнулся на сервере. Попробуйте ещё раз')
    expect(store.loaded).toBe(false)
    expect(store.loading).toBe(false)
  })

  it('старый ответ не затирает список нового фильтра', async () => {
    const store = useIssuesStore()
    store.status = 'resolved'
    const first = store.load()
    store.status = null
    const second = store.load()
    await Promise.all([first, second])
    expect(store.items).toHaveLength(7)
    expect(store.loading).toBe(false)
  })

  it('сброс при смене жителя очищает список и карточки', async () => {
    const store = useIssuesStore()
    await store.load()
    await store.fetchDetail(101)
    resetAllStores()
    expect(store.items).toEqual([])
    expect(store.details).toEqual({})
    expect(store.loaded).toBe(false)
  })
})

describe('стор заявок: карточка и голос', () => {
  it('карточка заявки обновляет строку в списке', async () => {
    const store = useIssuesStore()
    await store.load()
    const detail = await store.fetchDetail(103)
    expect(store.details[103]?.timeline.length).toBeGreaterThan(0)
    expect(detail.legal_basis).toBeTruthy()
    expect(byId(103)?.title).toBe('Не работает лифт в подъезде 1')
  })

  it('карточку не из списка не добавляет в список', async () => {
    const store = useIssuesStore()
    await store.fetchDetail(101)
    expect(store.items).toEqual([])
    expect(store.details[101]?.id).toBe(101)
  })

  it('голос сразу меняет счётчик, а сервер подтверждает', async () => {
    const store = useIssuesStore()
    await store.load()
    const pending = store.toggleVote(101)
    // до ответа сервера житель уже видит свой голос
    expect(byId(101)?.voted_by_me).toBe(true)
    expect(byId(101)?.votes_count).toBe(5)
    const data = await pending
    expect(data.voted_by_me).toBe(true)
    expect(data.votes_count).toBe(5)
    expect(store.details[101]?.voted_by_me).toBe(true)
  })

  it('повторное нажатие снимает голос', async () => {
    const store = useIssuesStore()
    await store.load()
    await store.fetchDetail(102)
    const data = await store.toggleVote(102)
    expect(data.voted_by_me).toBe(false)
    expect(data.votes_count).toBe(1)
    expect(byId(102)?.votes_count).toBe(1)
  })

  it('при ошибке сервера голос откатывается', async () => {
    const store = useIssuesStore()
    await store.load()
    await store.fetchDetail(101)
    breakServer()
    await expect(store.toggleVote(101)).rejects.toBeInstanceOf(ApiError)
    expect(byId(101)?.voted_by_me).toBe(false)
    expect(byId(101)?.votes_count).toBe(4)
    expect(store.details[101]?.votes_count).toBe(4)
  })

  it('за закрытую заявку голосовать нельзя, счётчик возвращается', async () => {
    const store = useIssuesStore()
    await store.load()
    const before = byId(106)?.votes_count
    await expect(store.toggleVote(106)).rejects.toThrow('Голосование уже закончилось')
    expect(byId(106)?.votes_count).toBe(before)
    expect(byId(106)?.voted_by_me).toBe(false)
  })

  it('голос за неизвестную заявку даёт понятную ошибку', async () => {
    await expect(useIssuesStore().toggleVote(999)).rejects.toThrow('Заявка не найдена')
  })

  it('смена статуса пишет запись в историю заявки', async () => {
    const store = useIssuesStore()
    await store.load()
    const data = await store.setStatus(103, 'in_progress', 'Мастер приедет к 15:00')
    expect(data.status).toBe('in_progress')
    expect(data.timeline.at(-1)?.note).toBe('Мастер приедет к 15:00')
    expect(byId(103)?.status_title).toBe('В работе')
  })
})
