import { defineStore } from 'pinia'
import { ref } from 'vue'
import { errorMessage } from '@/api/client'
import { assistantApi, devChatApi } from '@/api/endpoints'
import type { ChatMessage, ChatNotice, DevChat } from '@/api/types'
import { notify } from '@/lib/notify'
import { onRealtime } from '@/realtime/sse'
import { registerReset } from './helpers'

function isChatMessage(data: unknown): data is ChatMessage {
  return (
    !!data &&
    typeof data === 'object' &&
    'id' in data &&
    typeof (data as { chat_id?: unknown }).chat_id === 'number'
  )
}

/** Эмулятор группового чата MAX (только мок-режим). */
export const useDevChatStore = defineStore('devChat', () => {
  const chats = ref<DevChat[]>([])
  const currentChatId = ref<number | null>(null)
  const messages = ref<Record<number, ChatMessage[]>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadChats(): Promise<void> {
    if (chats.value.length > 0) return
    chats.value = await devChatApi.chats()
    if (currentChatId.value === null) currentChatId.value = chats.value[0]?.chat_id ?? null
  }

  async function loadMessages(chatId: number): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const list = await devChatApi.messages(chatId)
      messages.value = { ...messages.value, [chatId]: list }
    } catch (e) {
      error.value = errorMessage(e)
    } finally {
      loading.value = false
    }
  }

  /** Сообщение с тем же id заменяет старое: так приходят правки и удаления модератором. */
  function upsert(message: ChatMessage): void {
    const list = messages.value[message.chat_id]
    if (!list) return
    const index = list.findIndex((m) => m.id === message.id)
    const next =
      index === -1
        ? [...list, message]
        : [...list.slice(0, index), message, ...list.slice(index + 1)]
    messages.value = { ...messages.value, [message.chat_id]: next }
  }

  onRealtime('chat.message', (data) => {
    if (isChatMessage(data)) upsert(data)
  })

  // Ответ бота на нажатие callback-кнопки (всплывашка, как в MAX)
  onRealtime('chat.notice', (data) => {
    const notice = data as Partial<ChatNotice> | null
    if (notice?.text) notify.info(notice.text)
  })

  onRealtime('resync', () => {
    if (currentChatId.value !== null && messages.value[currentChatId.value]) {
      void loadMessages(currentChatId.value)
    }
  })

  // Список чатов зависит от жителя: личка с ботом у каждого своя
  registerReset(() => {
    chats.value = []
    currentChatId.value = null
    messages.value = {}
  })

  return { chats, currentChatId, messages, loading, error, loadChats, loadMessages }
})

export interface AssistantMessage {
  id: number
  role: 'user' | 'bot'
  text: string
  tools: string[]
  failed?: boolean
}

/** Личный чат с Кузей-ассистентом: история живёт до перезапуска приложения. */
export const useAssistantStore = defineStore('assistant', () => {
  const messages = ref<AssistantMessage[]>([])
  const typing = ref(false)
  let seq = 0

  async function send(text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed || typing.value) return
    messages.value = [...messages.value, { id: ++seq, role: 'user', text: trimmed, tools: [] }]
    typing.value = true
    try {
      const res = await assistantApi.chat(trimmed)
      messages.value = [
        ...messages.value,
        { id: ++seq, role: 'bot', text: res.reply, tools: res.tools_used ?? [] },
      ]
    } catch (e) {
      messages.value = [
        ...messages.value,
        {
          id: ++seq,
          role: 'bot',
          text: `Не получилось ответить: ${errorMessage(e)}`,
          tools: [],
          failed: true,
        },
      ]
    } finally {
      typing.value = false
    }
  }

  registerReset(() => {
    messages.value = []
  })

  return { messages, typing, send }
})
