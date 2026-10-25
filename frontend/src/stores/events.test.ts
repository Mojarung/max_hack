import { describe, expect, it, vi } from 'vitest'
import { breakServer, flushMock, NOW, useMockBackend } from '@/test/mockBackend'
import { useEventsStore } from './events'
import { resetAllStores } from './helpers'

useMockBackend()

const inDays = (days: number) => new Date(NOW.getTime() + days * 86_400_000).toISOString()

describe('стор событий: списки', () => {
  it('предстоящие идут по дате, ближайшее первым', async () => {
    const store = useEventsStore()
    await store.load('upcoming')
    const state = store.scopes.upcoming
    expect(state.loaded).toBe(true)
    expect(state.loading).toBe(false)
    expect(state.items.map((e) => e.id)).toEqual([301, 302, 303])
  })

  it('прошедшие идут от свежих к старым', async () => {
    const store = useEventsStore()
    await store.load('past')
    expect(store.scopes.past.items.map((e) => e.title)).toEqual([
      'Турнир по мини-футболу',
      'Весенний субботник',
    ])
  })

  it('ошибка сервера видна в своём списке, другой не трогает', async () => {
    breakServer()
    const store = useEventsStore()
    await store.load('upcoming')
    expect(store.scopes.upcoming.error).toBe('Кузя споткнулся на сервере. Попробуйте ещё раз')
    expect(store.scopes.upcoming.loading).toBe(false)
    expect(store.scopes.past.error).toBeNull()
  })

  it('сброс при смене жителя очищает всё', async () => {
    const store = useEventsStore()
    await store.load('upcoming')
    await store.fetchDetail(301)
    await store.loadComments(301)
    resetAllStores()
    expect(store.scopes.upcoming.items).toEqual([])
    expect(store.details).toEqual({})
    expect(store.comments).toEqual({})
  })
})

describe('стор событий: «Иду»', () => {
  it('записывает жителя сразу и подтверждает ответом сервера', async () => {
    const store = useEventsStore()
    await store.load('upcoming')
    await store.fetchDetail(301)
    const pending = store.toggleJoin(301)
    expect(store.details[301]?.joined_by_me).toBe(true)
    expect(store.scopes.upcoming.items[0]?.participants_count).toBe(5)
    const data = await pending
    expect(data.participants.map((p) => p.first_name)).toContain('Анна')
    expect(data.participants_count).toBe(5)
  })

  it('«Не иду» убирает жителя из участников', async () => {
    const store = useEventsStore()
    await store.load('upcoming')
    const data = await store.toggleJoin(302)
    expect(data.joined_by_me).toBe(false)
    expect(data.participants_count).toBe(1)
    expect(store.scopes.upcoming.items.find((e) => e.id === 302)?.joined_by_me).toBe(false)
  })

  it('при ошибке сервера возвращает как было', async () => {
    const store = useEventsStore()
    await store.load('upcoming')
    await store.fetchDetail(301)
    breakServer()
    await expect(store.toggleJoin(301)).rejects.toThrow('Кузя споткнулся')
    expect(store.details[301]?.joined_by_me).toBe(false)
    expect(store.details[301]?.participants_count).toBe(4)
    expect(store.scopes.upcoming.items[0]?.participants_count).toBe(4)
  })

  it('прошедшее событие тоже можно отметить из списка прошедших', async () => {
    const store = useEventsStore()
    await store.load('past')
    const data = await store.toggleJoin(304)
    expect(data.joined_by_me).toBe(false)
  })

  it('неизвестное событие даёт понятную ошибку', async () => {
    await expect(useEventsStore().toggleJoin(999)).rejects.toThrow('Событие не найдено')
  })
})

describe('стор событий: создание и правка', () => {
  it('новое событие встаёт в список по дате', async () => {
    const store = useEventsStore()
    await store.load('upcoming')
    const created = await store.create({
      title: 'Чаепитие у подъезда',
      description: 'Самовар и пироги',
      kind: 'holiday',
      starts_at: inDays(1),
      place: 'У второго подъезда',
    })
    expect(store.details[created.id]?.title).toBe('Чаепитие у подъезда')
    expect(store.scopes.upcoming.items[0]?.id).toBe(created.id)
    expect(created.joined_by_me).toBe(true)
  })

  it('если список ещё не загружен, создание его не трогает', async () => {
    const store = useEventsStore()
    await store.create({
      title: 'Собрание',
      description: '',
      kind: 'meeting',
      starts_at: inDays(2),
      place: 'Холл',
    })
    expect(store.scopes.upcoming.items).toEqual([])
  })

  it('организатор дописывает описание', async () => {
    const store = useEventsStore()
    await store.load('upcoming')
    const data = await store.updateDescription(303, '  Будет живая музыка  ')
    expect(data.description).toBe('Будет живая музыка')
    expect(store.scopes.upcoming.items.find((e) => e.id === 303)?.description).toBe(
      'Будет живая музыка',
    )
  })

  it('фото события добавляются с прогрессом и удаляются', async () => {
    const store = useEventsStore()
    const progress = vi.fn()
    const file = new File(['x'], 'yard.jpg', { type: 'image/jpeg' })
    const data = await store.addPhotos(301, [file, file], progress)
    expect(data.photos).toHaveLength(2)
    expect(progress).toHaveBeenLastCalledWith(1)
    const after = await store.removePhoto(301, 0)
    expect(after.photos).toHaveLength(1)
    expect(store.details[301]?.photos).toHaveLength(1)
  })
})

describe('стор событий: комментарии', () => {
  it('загружает обсуждение и добавляет свой комментарий в конец', async () => {
    const store = useEventsStore()
    await store.loadComments(301)
    expect(store.comments[301]).toHaveLength(4)
    const comment = await store.addComment(301, 'Возьму грабли')
    await flushMock()
    expect(store.comments[301]?.at(-1)).toMatchObject({ id: comment.id, text: 'Возьму грабли' })
  })

  it('комментарий к незагруженному обсуждению не создаёт список', async () => {
    const store = useEventsStore()
    await store.addComment(302, 'Приду')
    expect(store.comments[302]).toBeUndefined()
  })
})
