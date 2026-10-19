import { api, upload } from './client'
import type {
  AppMeta,
  AchievementsOut,
  AnnouncementOut,
  DocumentOut,
  DocumentScope,
  GeoResult,
  HouseBrief,
  HouseIn,
  ListingScope,
  Neighbour,
  ProfileOut,
  SyncOut,
  AlertOut,
  AssistantReply,
  Category,
  ChatMessage,
  Classification,
  CommentOut,
  DevChat,
  DevUser,
  EventDetail,
  EventKind,
  EventOut,
  IssueDetail,
  IssueOut,
  IssueStatus,
  ListingOut,
  ListingStatus,
  McpServerIn,
  McpServerOut,
  McpTool,
  MeOut,
  OkOut,
  PulseOut,
  SearchOut,
  ShelterOut,
} from './types'

export const meApi = {
  /** Без авторизации: ник бота и мок-режим сервера. */
  meta: () => api<AppMeta>('/meta', { timeoutMs: 6000 }),
  me: () => api<MeOut>('/me'),
  pulse: () => api<PulseOut>('/house/pulse'),
  devUsers: () => api<DevUser[]>('/dev/users', { timeoutMs: 6000 }),
  onboarded: () => api<MeOut>('/me/onboarded', { method: 'POST' }),
  /** Готовая картинка 1..9 вместо фото; null - вернуть фото из MAX. */
  setAvatar: (preset: number | null) =>
    api<MeOut>('/me/avatar', { method: 'PUT', body: { preset } }),
  uploadAvatar: (file: File, onProgress?: (fraction: number) => void) => {
    const form = new FormData()
    form.append('photo', file)
    return upload<MeOut>('/me/avatar/photo', form, onProgress)
  },
}

export const houseApi = {
  /** refresh=true: Кузя заново ищет чаты, где состоит житель, и добавляет дома. */
  list: (refresh = false) =>
    api<HouseBrief[]>('/houses', {
      query: { refresh: refresh ? 'true' : undefined },
      timeoutMs: 30_000,
    }),
  update: (body: HouseIn) => api<MeOut>('/house', { method: 'PATCH', body }),
  sync: () => api<SyncOut>('/house/sync', { method: 'POST', timeoutMs: 60_000 }),
  geocode: (q: string, signal?: AbortSignal) =>
    api<GeoResult[]>('/house/geocode', { query: { q }, signal, timeoutMs: 12_000 }),
}

export const announcementsApi = {
  list: () => api<AnnouncementOut[]>('/announcements'),
  create: (body: { title: string; text: string; pin: boolean }) =>
    api<AnnouncementOut>('/announcements', { method: 'POST', body }),
  pin: (id: number, pinned: boolean) =>
    api<AnnouncementOut>(`/announcements/${id}`, { method: 'PATCH', body: { pinned } }),
  remove: (id: number) => api<void>(`/announcements/${id}`, { method: 'DELETE' }),
}

export const documentsApi = {
  list: (scope?: DocumentScope) => api<DocumentOut[]>('/documents', { query: { scope } }),
  upload: (form: FormData, onProgress?: (fraction: number) => void) =>
    upload<DocumentOut>('/documents', form, onProgress),
  link: (id: number) => api<{ url: string; expires_at: number }>(`/documents/${id}/link`),
  remove: (id: number) => api<void>(`/documents/${id}`, { method: 'DELETE' }),
}

export const peopleApi = {
  list: () => api<Neighbour[]>('/people'),
  profile: (id: number) => api<ProfileOut>(`/people/${id}`),
  /** Спасибо соседу: +5 очков ему, раз в сутки. */
  thank: (id: number) => api<ProfileOut>(`/people/${id}/thanks`, { method: 'POST' }),
  /** Кузя перешлёт сообщение соседу в личку MAX. */
  message: (id: number, text: string) =>
    api<{ ok: boolean }>(`/people/${id}/message`, { method: 'POST', body: { text } }),
}

export const issuesApi = {
  list: (params: { status?: IssueStatus | null; q?: string }, signal?: AbortSignal) =>
    api<IssueOut[]>('/issues', { query: params, signal }),
  get: (id: number) => api<IssueDetail>(`/issues/${id}`),
  create: (form: FormData, onProgress?: (fraction: number) => void) =>
    upload<IssueDetail>('/issues', form, onProgress),
  similar: (text: string, signal?: AbortSignal) =>
    api<IssueOut[]>('/issues/similar', { method: 'POST', body: { text }, signal }),
  classify: (text: string, signal?: AbortSignal) =>
    api<Classification>('/issues/classify', { method: 'POST', body: { text }, signal }),
  vote: (id: number) => api<IssueDetail>(`/issues/${id}/vote`, { method: 'POST' }),
  unvote: (id: number) => api<IssueDetail>(`/issues/${id}/vote`, { method: 'DELETE' }),
  setStatus: (id: number, status: 'in_progress' | 'resolved' | 'rejected', note: string) =>
    api<IssueDetail>(`/issues/${id}/status`, { method: 'POST', body: { status, note } }),
}

export const listingsApi = {
  list: (
    params: { q?: string; category?: string | null; free?: boolean; scope?: ListingScope },
    signal?: AbortSignal,
  ) =>
    api<ListingOut[]>('/listings', {
      query: {
        q: params.q,
        category: params.category,
        free: params.free ? 'true' : undefined,
        scope: params.scope && params.scope !== 'active' ? params.scope : undefined,
      },
      signal,
    }),
  get: (id: number) => api<ListingOut>(`/listings/${id}`),
  categories: () => api<unknown>('/listings/categories'),
  create: (form: FormData, onProgress?: (fraction: number) => void) =>
    upload<ListingOut>('/listings', form, onProgress),
  setStatus: (id: number, status: ListingStatus) =>
    api<ListingOut>(`/listings/${id}`, { method: 'PATCH', body: { status } }),
  remove: (id: number) => api<void>(`/listings/${id}`, { method: 'DELETE' }),
  contact: (id: number, message: string) =>
    api<OkOut>(`/listings/${id}/contact`, { method: 'POST', body: { message } }),
}

export interface EventIn {
  title: string
  description: string
  kind: EventKind
  starts_at: string
  place: string
  max_participants?: number | null
}

export const eventsApi = {
  list: (scope: 'upcoming' | 'past') => api<EventOut[]>('/events', { query: { scope } }),
  get: (id: number) => api<EventDetail>(`/events/${id}`),
  create: (body: EventIn) => api<EventDetail>('/events', { method: 'POST', body }),
  /** Организатор дописывает описание уже созданного события. */
  update: (id: number, description: string) =>
    api<EventDetail>(`/events/${id}`, { method: 'PATCH', body: { description } }),
  addPhotos: (id: number, files: File[], onProgress?: (fraction: number) => void) => {
    const form = new FormData()
    for (const f of files) form.append('photos', f)
    return upload<EventDetail>(`/events/${id}/photos`, form, onProgress)
  },
  removePhoto: (id: number, index: number) =>
    api<EventDetail>(`/events/${id}/photos/${index}`, { method: 'DELETE' }),
  join: (id: number) => api<EventDetail>(`/events/${id}/join`, { method: 'POST' }),
  leave: (id: number) => api<EventDetail>(`/events/${id}/join`, { method: 'DELETE' }),
  comments: (id: number) => api<CommentOut[]>(`/events/${id}/comments`),
  comment: (id: number, text: string) =>
    api<CommentOut>(`/events/${id}/comments`, { method: 'POST', body: { text } }),
}

export const achievementsApi = {
  list: () => api<AchievementsOut>('/achievements'),
}

export const safetyApi = {
  shelters: (lat?: number, lon?: number) => api<ShelterOut[]>('/shelters', { query: { lat, lon } }),
  activeAlert: () => api<AlertOut | null>('/alerts/active'),
  startAlert: (message: string) =>
    api<AlertOut>('/alerts', { method: 'POST', body: { kind: 'drone', message } }),
  endAlert: (id: number) => api<AlertOut>(`/alerts/${id}/end`, { method: 'POST' }),
}

export const searchApi = {
  search: (q: string, signal?: AbortSignal) => api<SearchOut>('/search', { query: { q }, signal }),
}

export const assistantApi = {
  chat: (message: string) =>
    api<AssistantReply>('/assistant/chat', {
      method: 'POST',
      body: { message },
      timeoutMs: 60_000,
    }),
}

export const devChatApi = {
  chats: () => api<DevChat[]>('/dev/chats'),
  messages: (chatId: number) =>
    api<ChatMessage[]>('/dev/chat/messages', { query: { chat_id: chatId } }),
  /** Фото - data:-ссылки: бот получит их вложениями, как из настоящего MAX. */
  send: (chatId: number, userId: number, text: string, photos: string[] = []) =>
    api<OkOut>('/dev/chat/send', {
      method: 'POST',
      body: { chat_id: chatId, user_id: userId, text, photos },
      timeoutMs: 60_000,
    }),
  callback: (chatId: number, userId: number, messageId: string, payload: string) =>
    api<OkOut>('/dev/chat/callback', {
      method: 'POST',
      body: { chat_id: chatId, user_id: userId, message_id: messageId, payload },
      timeoutMs: 60_000,
    }),
}

export const mcpApi = {
  list: () => api<McpServerOut[]>('/mcp/servers'),
  create: (body: McpServerIn) => api<McpServerOut>('/mcp/servers', { method: 'POST', body }),
  remove: (id: number) => api<void>(`/mcp/servers/${id}`, { method: 'DELETE' }),
  tools: (id: number) => api<McpTool[]>(`/mcp/servers/${id}/tools`, { timeoutMs: 30_000 }),
}

/** Ответ `/listings/categories` не описан в контракте: принимаем массив строк, объектов или словарь. */
export function normalizeCategories(raw: unknown, fallback: Record<string, string>): Category[] {
  const title = (code: string) => fallback[code] ?? code
  if (Array.isArray(raw)) {
    return raw
      .map((item): Category | null => {
        if (typeof item === 'string') return { code: item, title: title(item) }
        if (item && typeof item === 'object') {
          const obj = item as Record<string, unknown>
          const code = String(obj.code ?? obj.id ?? obj.value ?? obj.category ?? '')
          if (!code) return null
          return { code, title: String(obj.title ?? obj.name ?? obj.label ?? title(code)) }
        }
        return null
      })
      .filter((c): c is Category => c !== null)
  }
  if (raw && typeof raw === 'object') {
    return Object.entries(raw as Record<string, unknown>).map(([code, value]) => ({
      code,
      title: typeof value === 'string' ? value : title(code),
    }))
  }
  return Object.entries(fallback).map(([code, t]) => ({ code, title: t }))
}
