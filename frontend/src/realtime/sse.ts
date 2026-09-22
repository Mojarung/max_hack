import { ref } from 'vue'
import { API_BASE, authQuery } from '@/api/client'

export const REALTIME_EVENTS = [
  'issue.created',
  'issue.updated',
  'listing.created',
  'listing.updated',
  'event.created',
  'event.updated',
  'comment.created',
  'alert.started',
  'alert.ended',
  'achievement.awarded',
  'pulse.changed',
  'chat.message',
  'chat.notice',
] as const

export type RealtimeEvent = (typeof REALTIME_EVENTS)[number] | 'resync'
type Handler = (data: unknown) => void

export type RealtimeStatus = 'idle' | 'connecting' | 'open' | 'reconnecting'

/** Состояние подключения для индикатора в шапке. */
export const realtimeStatus = ref<RealtimeStatus>('idle')

const handlers = new Map<RealtimeEvent, Set<Handler>>()
let source: EventSource | null = null
let retryTimer: ReturnType<typeof setTimeout> | null = null
let attempt = 0
let hadConnection = false

export function onRealtime(type: RealtimeEvent, handler: Handler): () => void {
  let set = handlers.get(type)
  if (!set) {
    set = new Set()
    handlers.set(type, set)
  }
  set.add(handler)
  return () => set.delete(handler)
}

function emit(type: RealtimeEvent, data: unknown): void {
  handlers.get(type)?.forEach((handler) => {
    try {
      handler(data)
    } catch (error) {
      console.error('[realtime]', type, error)
    }
  })
}

function parse(raw: string): unknown {
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

export function connectRealtime(): void {
  disconnectRealtime()
  if (typeof EventSource === 'undefined') return
  realtimeStatus.value = hadConnection ? 'reconnecting' : 'connecting'
  const url = `${API_BASE}/realtime/stream?${authQuery().toString()}`
  const es = new EventSource(url)
  source = es

  es.onopen = () => {
    realtimeStatus.value = 'open'
    // После обрыва сообщаем сторам: пропущенные события надо добрать запросом.
    if (hadConnection || attempt > 0) emit('resync', null)
    hadConnection = true
    attempt = 0
  }

  es.onerror = () => {
    if (source !== es) return
    realtimeStatus.value = 'reconnecting'
    if (es.readyState === EventSource.CLOSED) scheduleReconnect()
  }

  for (const type of REALTIME_EVENTS) {
    es.addEventListener(type, (event) => emit(type, parse((event as MessageEvent<string>).data)))
  }
}

function scheduleReconnect(): void {
  if (retryTimer) return
  attempt += 1
  const delay = Math.min(30_000, 1000 * 2 ** Math.min(attempt, 5))
  retryTimer = setTimeout(() => {
    retryTimer = null
    connectRealtime()
  }, delay)
}

export function disconnectRealtime(): void {
  if (retryTimer) {
    clearTimeout(retryTimer)
    retryTimer = null
  }
  if (source) {
    source.close()
    source = null
  }
  realtimeStatus.value = 'idle'
}

/** Простейшая проверка, что в событии пришла сущность с числовым id. */
export function hasNumericId(data: unknown): data is { id: number } {
  return !!data && typeof data === 'object' && typeof (data as { id?: unknown }).id === 'number'
}
