import { describe, expect, it, vi } from 'vitest'
import { devChatApi } from '@/api/endpoints'
import { breakServer, useMockBackend } from '@/test/mockBackend'
import { useAssistantStore, useDevChatStore } from './chat'
import { resetAllStores } from './helpers'

useMockBackend()

describe('эмулятор чата MAX', () => {
  it('загружает чаты один раз и выбирает первый', async () => {
    const spy = vi.spyOn(devChatApi, 'chats')
    const store = useDevChatStore()
    await store.loadChats()
    await store.loadChats()
    expect(spy).toHaveBeenCalledTimes(1)
    expect(store.chats[0]?.title).toBe('Ленинского Комсомола, 5 - домовой чат')
    expect(store.currentChatId).toBe(1)
  })

  it('не меняет уже выбранный чат', async () => {
    const store = useDevChatStore()
    store.currentChatId = 7
    await store.loadChats()
    expect(store.currentChatId).toBe(7)
  })

  it('загружает сообщения чата', async () => {
    const store = useDevChatStore()
    await store.loadMessages(1)
    expect(store.messages[1]).toEqual([])
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('ошибка загрузки сообщений видна', async () => {
    breakServer()
    const store = useDevChatStore()
    await store.loadMessages(1)
    expect(store.error).toBe('Кузя споткнулся на сервере. Попробуйте ещё раз')
    expect(store.loading).toBe(false)
  })

  it('сброс при смене жителя забывает чаты', async () => {
    const store = useDevChatStore()
    await store.loadChats()
    await store.loadMessages(1)
    resetAllStores()
    expect(store.chats).toEqual([])
    expect(store.currentChatId).toBeNull()
    expect(store.messages).toEqual({})
  })
})

describe('личный чат с Кузей', () => {
  it('показывает вопрос жителя и ответ Кузи с тем, что он смотрел', async () => {
    const store = useAssistantStore()
    const pending = store.send('  Когда вывезут мусор?  ')
    expect(store.typing).toBe(true)
    expect(store.messages[0]).toMatchObject({ role: 'user', text: 'Когда вывезут мусор?' })
    await pending
    expect(store.typing).toBe(false)
    const reply = store.messages[1]
    expect(reply?.role).toBe('bot')
    expect(reply?.text).toContain('Вы спросили: «Когда вывезут мусор?»')
    expect(reply?.tools).toEqual(['get_pulse', 'search_issues'])
  })

  it('пустое сообщение и повтор во время ответа не отправляются', async () => {
    const store = useAssistantStore()
    await store.send('   ')
    expect(store.messages).toEqual([])
    const first = store.send('Привет')
    await store.send('Ещё раз')
    await first
    expect(store.messages.filter((m) => m.role === 'user')).toHaveLength(1)
  })

  it('если Кузя не ответил, это видно в чате', async () => {
    breakServer()
    const store = useAssistantStore()
    await store.send('Привет')
    expect(store.messages[1]).toMatchObject({
      role: 'bot',
      failed: true,
      text: 'Не получилось ответить: Кузя споткнулся на сервере. Попробуйте ещё раз',
    })
  })

  it('сброс при смене жителя очищает историю', async () => {
    const store = useAssistantStore()
    await store.send('Привет')
    resetAllStores()
    expect(store.messages).toEqual([])
  })
})
