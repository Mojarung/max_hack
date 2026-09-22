/** Типы по контракту docs/API.md. Имена полей совпадают с бэкендом. */

export type Mood = 'happy' | 'ok' | 'worried' | 'sad' | 'alarm'
export type Role = 'resident' | 'admin'

export interface UserShort {
  id: number
  max_user_id?: number
  first_name: string
  last_name?: string | null
  photo_url?: string | null
  apartment?: string | null
}

export interface UserFull extends UserShort {
  max_user_id: number
  username?: string | null
  points: number
  level: number
  level_title: string
  next_level_points: number | null
}

export interface House {
  id: number
  title: string
  address: string
  lat: number
  lon: number
  members_count: number
  vote_threshold_pct: number
  /** Название управляющей компании дома. */
  uk_name?: string | null
}

export interface MeOut {
  user: UserFull
  house: House
  role: Role
  mock: boolean
  /** Ник бота в MAX для ссылки «Написать Кузе». */
  bot_username?: string | null
}

export interface PulseStats {
  open_issues: number
  overdue_issues: number
  resolved_30d: number
  upcoming_events: number
  active_listings: number
  active_alert: boolean
}

export interface PulseOut {
  mood: Mood
  score: number
  level: number
  xp: number
  xp_next: number
  phrase: string
  stats: PulseStats
}

/** Демо-житель для мок-режима. Контракт описывает только max_user_id. */
export interface DevUser {
  max_user_id: number
  first_name: string
  last_name?: string | null
  apartment?: string | null
  role?: Role
  id?: number
}

export type IssueStatus = 'voting' | 'sent' | 'in_progress' | 'resolved' | 'rejected'

export interface ResponsibleOrg {
  name: string
  kind: string
  kind_title: string
}

export interface IssueOut {
  id: number
  title: string
  description: string
  category: string
  category_title: string
  status: IssueStatus
  status_title: string
  votes_count: number
  votes_needed: number
  voted_by_me: boolean
  photos: string[]
  author: UserShort
  responsible_org: ResponsibleOrg | null
  created_at: string
  sent_at: string | null
  deadline_at: string | null
  is_overdue: boolean
  score: number | null
}

export interface TimelineEntry {
  status: IssueStatus
  status_title: string
  note: string | null
  created_at: string
}

export interface IssueDetail extends IssueOut {
  legal_basis: string | null
  deadline_hours: number | null
  appeal_text: string | null
  location_hint: string | null
  timeline: TimelineEntry[]
}

export interface Classification {
  category: string
  category_title: string
  org_kind: string
  org_name: string
  legal_basis: string
  deadline_hours: number
  confidence: number
  source: 'llm' | 'rules'
}

export type ListingStatus = 'active' | 'reserved' | 'closed'

export interface ListingOut {
  id: number
  title: string
  description: string
  price: number
  is_free: boolean
  category: string
  category_title: string
  status: ListingStatus
  photos: string[]
  author: UserShort
  is_mine: boolean
  created_at: string
  score?: number | null
}

export interface Category {
  code: string
  title: string
}

export type EventKind = 'subbotnik' | 'meeting' | 'holiday' | 'sport' | 'kids' | 'other'

export interface EventOut {
  id: number
  title: string
  description: string
  kind: EventKind
  kind_title: string
  starts_at: string
  place: string
  max_participants: number | null
  participants_count: number
  joined_by_me: boolean
  comments_count: number
  author: UserShort
  created_at: string
  score?: number | null
}

export interface EventDetail extends EventOut {
  participants: UserShort[]
}

export interface CommentOut {
  id: number
  event_id: number
  author: UserShort
  text: string
  created_at: string
}

export interface AchievementOut {
  code: string
  title: string
  description: string
  icon: string
  points: number
  earned: boolean
  awarded_at: string | null
}

export interface LeaderRow {
  rank: number
  user: UserShort
  points: number
  level_title: string
  is_me?: boolean
}

export interface AchievementsOut {
  items: AchievementOut[]
  leaderboard: LeaderRow[]
}

export interface ShelterOut {
  id: number
  name: string
  address: string
  lat: number
  lon: number
  capacity: number | null
  kind: string
  distance_m: number | null
  yandex_url: string
  osm_url: string
}

export interface AlertOut {
  id: number
  kind: string
  kind_title: string
  message: string | null
  active: boolean
  created_at: string
  ended_at: string | null
}

export interface SearchOut {
  issues: IssueOut[]
  events: EventOut[]
  listings: ListingOut[]
}

export interface AssistantReply {
  reply: string
  tools_used: string[]
}

export type ChatButtonType = 'callback' | 'link' | 'open_app'

export interface ChatButton {
  type: ChatButtonType
  text: string
  payload?: string | null
  url?: string | null
}

export interface ChatMessage {
  id: string
  chat_id: number
  from: { user_id: number; name: string } | null
  text: string
  buttons: ChatButton[][] | null
  deleted: boolean
  notice: string | null
  created_at: string
}

export interface DevChat {
  chat_id: number
  title: string
  type: 'chat' | 'dialog'
}

export type McpTransport = 'streamable_http' | 'sse'

export interface McpServerOut {
  id: number
  name: string
  transport: McpTransport
  url: string
  enabled: boolean
  has_headers: boolean
}

/** Имя MCP-сервера: латиница в нижнем регистре, цифры и _, 2-31 символ. */
export const MCP_NAME_RE = /^[a-z][a-z0-9_]{1,30}$/

export interface McpServerIn {
  name: string
  transport: McpTransport
  url: string
  headers: Record<string, string>
}

export interface McpTool {
  name: string
  description: string | null
}

export interface ChatNotice {
  callback_id: string
  text: string
}

export interface OkOut {
  ok: boolean
}
