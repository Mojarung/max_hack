import { defineStore } from 'pinia'
import { ref } from 'vue'
import { errorMessage } from '@/api/client'
import { eventsApi, type EventIn } from '@/api/endpoints'
import type { CommentOut, EventDetail, EventOut } from '@/api/types'
import { hasNumericId, onRealtime } from '@/realtime/sse'
import { registerReset, upsertById } from './helpers'

export type EventScope = 'upcoming' | 'past'

interface ScopeState {
  items: EventOut[]
  loaded: boolean
  loading: boolean
  error: string | null
}

function emptyScope(): ScopeState {
  return { items: [], loaded: false, loading: false, error: null }
}

const PERSONAL_KEYS: (keyof EventOut)[] = ['joined_by_me']

export const useEventsStore = defineStore('events', () => {
  const scopes = ref<Record<EventScope, ScopeState>>({
    upcoming: emptyScope(),
    past: emptyScope(),
  })
  const details = ref<Record<number, EventDetail>>({})
  const comments = ref<Record<number, CommentOut[]>>({})

  function patchScope(scope: EventScope, patch: Partial<ScopeState>): void {
    scopes.value = { ...scopes.value, [scope]: { ...scopes.value[scope], ...patch } }
  }

  async function load(scope: EventScope): Promise<void> {
    patchScope(scope, { loading: true, error: null })
    try {
      const items = await eventsApi.list(scope)
      patchScope(scope, { items, loaded: true })
    } catch (e) {
      patchScope(scope, { error: errorMessage(e) })
    } finally {
      patchScope(scope, { loading: false })
    }
  }

  function patchLists(event: EventOut, keepPersonal: boolean): void {
    for (const scope of ['upcoming', 'past'] as EventScope[]) {
      const state = scopes.value[scope]
      patchScope(scope, {
        items: upsertById(state.items, event, {
          onlyExisting: true,
          keep: keepPersonal ? PERSONAL_KEYS : [],
        }),
      })
    }
  }

  function storeDetail(detail: EventDetail): void {
    details.value = { ...details.value, [detail.id]: detail }
    patchLists(detail, false)
  }

  async function fetchDetail(id: number): Promise<EventDetail> {
    const data = await eventsApi.get(id)
    storeDetail(data)
    return data
  }

  async function create(body: EventIn): Promise<EventDetail> {
    const data = await eventsApi.create(body)
    storeDetail(data)
    const upcoming = scopes.value.upcoming
    if (upcoming.loaded)
      patchScope('upcoming', { items: sortByDate(upsertById(upcoming.items, data)) })
    return data
  }

  /** «Иду / не иду» с оптимистичным обновлением. */
  async function toggleJoin(id: number): Promise<EventDetail> {
    const detail = details.value[id]
    const listItem =
      scopes.value.upcoming.items.find((e) => e.id === id) ??
      scopes.value.past.items.find((e) => e.id === id)
    const base = detail ?? listItem
    if (!base) throw new Error('Событие не найдено')
    const joining = !base.joined_by_me
    const optimistic = {
      joined_by_me: joining,
      participants_count: Math.max(0, base.participants_count + (joining ? 1 : -1)),
    }
    if (detail) details.value = { ...details.value, [id]: { ...detail, ...optimistic } }
    if (listItem) patchLists({ ...listItem, ...optimistic }, false)
    try {
      const data = joining ? await eventsApi.join(id) : await eventsApi.leave(id)
      storeDetail(data)
      return data
    } catch (e) {
      if (detail) details.value = { ...details.value, [id]: detail }
      if (listItem) patchLists(listItem, false)
      throw e
    }
  }

  async function loadComments(eventId: number): Promise<void> {
    const data = await eventsApi.comments(eventId)
    comments.value = { ...comments.value, [eventId]: data }
  }

  function appendComment(comment: CommentOut): void {
    const list = comments.value[comment.event_id]
    if (!list || list.some((c) => c.id === comment.id)) return
    comments.value = { ...comments.value, [comment.event_id]: [...list, comment] }
  }

  async function addComment(eventId: number, text: string): Promise<CommentOut> {
    const comment = await eventsApi.comment(eventId, text)
    appendComment(comment)
    return comment
  }

  function sortByDate(list: EventOut[]): EventOut[] {
    return [...list].sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at))
  }

  onRealtime('event.created', (data) => {
    if (!hasNumericId(data)) return
    const event = data as EventOut
    const upcoming = scopes.value.upcoming
    if (upcoming.loaded && Date.parse(event.starts_at) >= Date.now()) {
      patchScope('upcoming', { items: sortByDate(upsertById(upcoming.items, event)) })
    }
  })

  onRealtime('event.updated', (data) => {
    if (!hasNumericId(data)) return
    const event = data as EventOut
    patchLists(event, true)
    const cached = details.value[event.id]
    if (cached) {
      details.value = {
        ...details.value,
        [event.id]: { ...cached, ...event, joined_by_me: cached.joined_by_me },
      }
      // Список участников приходит только в детальной карточке
      fetchDetail(event.id).catch(() => undefined)
    }
  })

  onRealtime('comment.created', (data) => {
    if (!hasNumericId(data)) return
    const comment = data as CommentOut
    if (typeof comment.event_id === 'number') appendComment(comment)
  })

  onRealtime('resync', () => {
    for (const scope of ['upcoming', 'past'] as EventScope[]) {
      if (scopes.value[scope].loaded) void load(scope)
    }
    for (const id of Object.keys(comments.value))
      void loadComments(Number(id)).catch(() => undefined)
  })

  registerReset(() => {
    scopes.value = { upcoming: emptyScope(), past: emptyScope() }
    details.value = {}
    comments.value = {}
  })

  return {
    scopes,
    details,
    comments,
    load,
    fetchDetail,
    create,
    toggleJoin,
    loadComments,
    addComment,
  }
})
