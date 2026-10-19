/**
 * Мок-бэкенд в памяти вкладки. Подключается при VITE_MOCK_API=true (`npm run dev:mock`)
 * или в демо из браузера (`src/api/mode.ts`); отдельным чанком, который грузится только
 * в этих режимах. Действия (голос, «Иду», новая заявка) меняют состояние до перезагрузки
 * страницы, так что сценарии можно пройти целиком, не трогая настоящую базу и домовой чат.
 */
import { ApiError, getDevUser, getHouseId } from '@/api/client'
import type {
  AchievementsOut,
  AnnouncementOut,
  DocumentOut,
  House,
  HouseBrief,
  Neighbour,
  ProfileOut,
  AlertOut,
  Classification,
  CommentOut,
  EventDetail,
  EventOut,
  IssueDetail,
  IssueOut,
  ListingOut,
  MeOut,
  Mood,
  PulseOut,
} from '@/api/types'
import {
  HOUSE,
  MCP_SERVERS,
  SHELTERS,
  buildAchievements,
  buildAlert,
  buildComments,
  buildEvents,
  buildIssue,
  buildIssues,
  buildListings,
  buildUsers,
  classifyText,
  short,
} from './fixtures'
import { presetAvatar } from '@/utils/avatar'
import { scenario } from './scenario'
import { LISTING_CATEGORY_TITLES } from '@/utils/labels'

const users = buildUsers(scenario)
let me = scenario.role === 'admin' ? users[1]! : users[0]!
/** Кто кого поблагодарил в этой вкладке: «кто:кому». */
const thanked = new Set<string>()
const needed = Math.max(3, Math.ceil((HOUSE.members_count * HOUSE.vote_threshold_pct) / 100))

/** Второй дом того же жителя: видно переключение домов. */
const HOUSE2: House = {
  ...HOUSE,
  id: 2,
  title: 'Созидателей, 34',
  address: 'Ульяновск, пр-т Созидателей, 34',
  members_count: 24,
  info: '',
  setup_done: true,
}
const houses: House[] = [
  {
    ...HOUSE,
    info: 'Диспетчерская УК: +7 (8422) 00-00-01, круглосуточно.\nПредседатель совета дома: Анна Петрова, кв. 12.',
    uk_email: 'uk@example.org',
    uk_phone: '+7 (8422) 00-00-01',
    setup_done: !scenario.setup,
    has_chat: true,
    bot_is_admin: true,
    is_demo: true,
  },
  HOUSE2,
]
if (scenario.setup) Object.assign(houses[0]!, { address: '', uk_name: null, info: '' })
me.onboarded = !scenario.onboarding
const currentHouse = (): House => houses.find((h) => h.id === getHouseId()) ?? houses[0]!

const db = {
  announcements: [
    {
      id: 901,
      title: 'Отключение горячей воды 1-3 октября',
      text: 'Плановые работы на теплотрассе. Воду дадут 3 октября к 18:00 (по данным УК).',
      pinned: true,
      event_id: null,
      author: null,
      is_mine: false,
      created_at: new Date(Date.now() - 5 * 3_600_000).toISOString(),
    },
    {
      id: 902,
      title: 'Покраска подъезда 2',
      text: 'С понедельника красят стены на 1-4 этажах. Не ставьте, пожалуйста, велосипеды у стен.',
      pinned: false,
      event_id: null,
      author: null,
      is_mine: false,
      created_at: new Date(Date.now() - 30 * 3_600_000).toISOString(),
    },
  ] as AnnouncementOut[],
  documents: [
    {
      id: 801,
      title: 'Протокол общего собрания от 12.09',
      filename: 'protokol-12-09.pdf',
      content_type: 'application/pdf',
      size: 184_320,
      scope: 'house',
      author: null,
      can_delete: scenario.role === 'admin',
      created_at: new Date(Date.now() - 9 * 86_400_000).toISOString(),
    },
    {
      id: 802,
      title: 'Договор управления с УК',
      filename: 'dogovor-upravleniya.pdf',
      content_type: 'application/pdf',
      size: 612_000,
      scope: 'house',
      author: null,
      can_delete: scenario.role === 'admin',
      created_at: new Date(Date.now() - 60 * 86_400_000).toISOString(),
    },
  ] as DocumentOut[],
  issues: buildIssues(scenario, users, needed),
  listings: buildListings(scenario, users, me.id),
  events: buildEvents(scenario, users),
  comments: buildComments(users),
  achievements: buildAchievements(scenario),
  alert: buildAlert(scenario) as AlertOut | null,
  nextId: 1000,
}

type Query = Record<string, string | number | boolean | null | undefined>
type Body = Record<string, unknown>
type Handler = (params: string[], query: Query, body: Body) => unknown

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const notFound = () => new ApiError('http', 404, 'Не нашли: возможно, запись уже удалили')
const toOut = ({
  legal_basis,
  deadline_hours,
  appeal_text,
  location_hint,
  timeline,
  ...rest
}: IssueDetail): IssueOut => {
  void [legal_basis, deadline_hours, appeal_text, location_hint, timeline]
  return rest
}
const eventOut = ({ participants, ...rest }: EventDetail): EventOut => {
  void participants
  return rest
}
const matches = (q: unknown, ...fields: string[]) => {
  const needle = String(q ?? '')
    .trim()
    .toLowerCase()
  return !needle || fields.some((f) => f.toLowerCase().includes(needle))
}

/** Кто поддержал заявку: в демо жителей переключают, и голос у каждого свой. */
const voters = new Map<number, Set<number>>()

function votersOf(i: IssueDetail): Set<number> {
  let set = voters.get(i.id)
  if (!set) {
    set = new Set(i.voted_by_me ? [me.id] : [])
    voters.set(i.id, set)
  }
  return set
}

/** Житель из переключателя (X-Dev-User) становится «мной»: голоса и «Иду» пересчитываются. */
function syncMe(): void {
  const next = users.find((u) => u.max_user_id === getDevUser())
  if (!next || next === me) return
  for (const i of db.issues) votersOf(i)
  me = next
  for (const i of db.issues) i.voted_by_me = votersOf(i).has(me.id)
  for (const e of db.events) e.joined_by_me = e.participants.some((p) => p.id === me.id)
}

function issue(id: string): IssueDetail {
  const found = db.issues.find((i) => i.id === Number(id))
  if (!found) throw notFound()
  return found
}

function event(id: string): EventDetail {
  const found = db.events.find((e) => e.id === Number(id))
  if (!found) throw notFound()
  return found
}

function listing(id: string): ListingOut {
  const found = db.listings.find((l) => l.id === Number(id))
  if (!found) throw notFound()
  return found
}

function refreshOverdue(): void {
  for (const i of db.issues) {
    i.is_overdue =
      !!i.deadline_at &&
      new Date(i.deadline_at).getTime() < Date.now() &&
      ['sent', 'in_progress'].includes(i.status)
  }
}

function pulse(): PulseOut {
  refreshOverdue()
  const open = db.issues.filter((i) => ['voting', 'sent', 'in_progress'].includes(i.status)).length
  const overdue = db.issues.filter((i) => i.is_overdue).length
  const resolved = db.issues.filter((i) => i.status === 'resolved').length
  const upcoming = db.events.filter((e) => new Date(e.starts_at).getTime() > Date.now()).length
  const score = Math.max(
    5,
    Math.min(100, 92 - open * 5 - overdue * 12 + resolved * 4 + upcoming * 2),
  )
  const mood: Mood = db.alert
    ? 'alarm'
    : overdue >= 2
      ? 'sad'
      : overdue === 1
        ? 'worried'
        : score >= 75
          ? 'happy'
          : 'ok'
  const phrase = db.alert
    ? 'Тревога! Отойдите от окон и идите в укрытие, я покажу ближайшее.'
    : overdue >= 2
      ? `Уже ${overdue} заявки просрочены. Я подготовил жалобу в Госжилинспекцию.`
      : overdue === 1
        ? 'Баки у первого подъезда так и не вывезли, срок вышел. Готовлю жалобу.'
        : open === 0
          ? 'В доме тишь да гладь. Может, устроим субботник?'
          : `Открытых заявок: ${open}. Поддержите соседей голосом, вместе быстрее.`
  return {
    mood,
    score,
    level: scenario.name === 'empty' ? 1 : 3,
    xp: scenario.name === 'empty' ? 0 : 340,
    xp_next: 500,
    phrase,
    stats: {
      open_issues: open,
      overdue_issues: overdue,
      resolved_30d: resolved,
      upcoming_events: upcoming,
      active_listings: db.listings.filter((l) => l.status === 'active').length,
      active_alert: !!db.alert,
      awaiting_my_vote: db.issues.filter(
        (i) => i.status === 'voting' && !i.voted_by_me && i.author?.id !== me.id,
      ).length,
    },
  }
}

function neighbour(u: (typeof users)[number], i: number): Neighbour {
  return {
    id: u.id,
    first_name: u.first_name,
    last_name: u.last_name ?? '',
    photo_url: u.photo_url ?? null,
    apartment: u.apartment ?? null,
    role: i === 1 ? 'admin' : 'resident',
    points: u.points,
    level_title: u.level_title,
  }
}

function profile(id: number): ProfileOut {
  const i = users.findIndex((u) => u.id === id)
  if (i < 0) throw notFound()
  const u = users[i]!
  const mine = db.issues.filter((x) => x.author.id === id)
  return {
    user: neighbour(u, i),
    is_me: u.id === me.id,
    thanks_count: [...thanked].filter((t) => t.endsWith(`:${u.id}`)).length,
    thanked_by_me: thanked.has(`${me.id}:${u.id}`),
    username: null,
    member_since: new Date(Date.now() - (120 + i * 30) * 86_400_000).toISOString(),
    level: u.level,
    next_level_points: u.next_level_points,
    stats: {
      issues_created: mine.length,
      issues_open: mine.filter((x) => ['voting', 'sent', 'in_progress'].includes(x.status)).length,
      votes: 3 + i,
      events_joined: 2,
      listings_active: db.listings.filter((l) => l.author.id === id && l.status !== 'closed')
        .length,
    },
    achievements: db.achievements
      .filter((a) => a.earned && u.id === me.id)
      .map((a) => ({ code: a.code, title: a.title, icon: a.icon, awarded_at: a.awarded_at ?? '' })),
  }
}

function housesOut(): HouseBrief[] {
  const current = currentHouse().id
  return houses.map((h, i) => ({
    id: h.id,
    title: h.title,
    address: h.address,
    role: i === 0 ? scenario.role : 'resident',
    is_demo: false,
    is_current: h.id === current,
  }))
}

function meOut(): MeOut {
  return {
    user: me,
    house: currentHouse(),
    role: scenario.role,
    mock: !scenario.inMax,
    bot_username: 'domovoy_kuzya_bot',
  }
}

function vote(id: string, on: boolean): IssueDetail {
  const i = issue(id)
  if (i.status !== 'voting') throw new ApiError('http', 409, 'Голосование уже закончилось')
  const set = votersOf(i)
  if (set.has(me.id) === on) return i
  if (on) set.add(me.id)
  else set.delete(me.id)
  i.voted_by_me = on
  i.votes_count += on ? 1 : -1
  if (i.votes_count >= i.votes_needed) {
    const hours = i.deadline_hours ?? 24
    Object.assign(i, {
      status: 'sent',
      status_title: 'Отправлено',
      sent_at: new Date().toISOString(),
      deadline_at: new Date(Date.now() + hours * 3_600_000).toISOString(),
      appeal_text: `${i.responsible_org?.name}\nот жителей дома по адресу: ${HOUSE.address}\n\nОБРАЩЕНИЕ\n\n${i.description}\n\nОбращение поддержали ${i.votes_count} жителей дома.`,
    })
    i.timeline.push({
      status: 'sent',
      status_title: 'Отправлено',
      note: `Обращение отправлено: ${i.responsible_org?.name}`,
      created_at: new Date().toISOString(),
    })
  }
  return i
}

function join(id: string, on: boolean): EventDetail {
  const e = event(id)
  if (e.joined_by_me === on) return e
  e.joined_by_me = on
  e.participants = on
    ? [...e.participants, short(me)]
    : e.participants.filter((p) => p.id !== me.id)
  e.participants_count = e.participants.length
  return e
}

function classification(text: string): Classification {
  const rule = classifyText(text)
  return {
    category: rule.code,
    category_title: rule.title,
    org_kind: rule.org.kind,
    org_name: rule.org.name,
    legal_basis: rule.basis,
    deadline_hours: rule.hours,
    confidence: rule.code === 'other' ? 0.4 : 0.9,
    source: 'rules',
  }
}

const routes: [string, RegExp, Handler][] = [
  ['GET', /^\/meta$/, () => ({ bot_username: 'domovoy_kuzya_bot', mock: true })],
  ['GET', /^\/me$/, () => meOut()],
  [
    'POST',
    /^\/me\/onboarded$/,
    () => {
      me.onboarded = true
      return meOut()
    },
  ],
  [
    'PUT',
    /^\/me\/avatar$/,
    (_, __, b) => {
      const preset = (b as { preset: number | null }).preset
      me.avatar = preset ? `preset:${preset}` : null
      me.photo_url = preset ? presetAvatar(preset) : null
      return meOut()
    },
  ],
  ['GET', /^\/houses$/, () => housesOut()],
  [
    'PATCH',
    /^\/house$/,
    (_, __, b) => {
      const { apartment, ...fields } = b as Record<string, unknown>
      if (Object.keys(fields).length && scenario.role !== 'admin')
        throw new ApiError('http', 403, 'Настройки дома меняет администратор')
      Object.assign(currentHouse(), fields)
      if (typeof apartment === 'string') me.apartment = apartment || null
      return meOut()
    },
  ],
  [
    'POST',
    /^\/house\/sync$/,
    () => ({ members: currentHouse().members_count, bot_is_admin: true }),
  ],
  [
    'GET',
    /^\/house\/geocode$/,
    (_, q) => [
      { title: `${String(q.q)}, Ульяновск, Ульяновская область`, lat: 54.3857, lon: 48.6072 },
      { title: `${String(q.q)}, Димитровград, Ульяновская область`, lat: 54.2138, lon: 49.6184 },
    ],
  ],
  [
    'GET',
    /^\/announcements$/,
    () =>
      [...db.announcements].sort(
        (a, b) => Number(b.pinned) - Number(a.pinned) || b.created_at.localeCompare(a.created_at),
      ),
  ],
  [
    'POST',
    /^\/announcements$/,
    (_, __, b) => {
      const created: AnnouncementOut = {
        id: db.nextId++,
        title: String(b.title),
        text: String(b.text ?? ''),
        pinned: !!b.pin && scenario.role === 'admin',
        event_id: null,
        author: short(me),
        is_mine: true,
        created_at: new Date().toISOString(),
      }
      db.announcements.unshift(created)
      return created
    },
  ],
  [
    'PATCH',
    /^\/announcements\/(\d+)$/,
    ([id], _, b) => {
      const a = db.announcements.find((x) => x.id === Number(id))
      if (!a) throw notFound()
      a.pinned = !!b.pinned
      return a
    },
  ],
  [
    'DELETE',
    /^\/announcements\/(\d+)$/,
    ([id]) => {
      db.announcements = db.announcements.filter((x) => x.id !== Number(id))
      return undefined
    },
  ],
  ['GET', /^\/documents$/, (_, q) => db.documents.filter((d) => !q.scope || d.scope === q.scope)],
  [
    'GET',
    /^\/documents\/(\d+)\/link$/,
    ([id]) => {
      const d = db.documents.find((x) => x.id === Number(id))
      if (!d) throw notFound()
      const blob = new Blob([`Демо-документ «${d.title}»`], { type: 'text/plain;charset=utf-8' })
      return { url: URL.createObjectURL(blob), expires_at: Date.now() / 1000 + 900 }
    },
  ],
  [
    'DELETE',
    /^\/documents\/(\d+)$/,
    ([id]) => {
      db.documents = db.documents.filter((x) => x.id !== Number(id))
      return undefined
    },
  ],
  ['GET', /^\/people$/, () => users.map(neighbour)],
  ['GET', /^\/people\/(\d+)$/, ([id]) => profile(Number(id))],
  [
    'POST',
    /^\/people\/(\d+)\/thanks$/,
    ([id]) => {
      const target = users.find((u) => u.id === Number(id))
      if (!target) throw notFound()
      if (target.id === me.id) throw new ApiError('http', 409, 'Себя поблагодарить нельзя')
      const key = `${me.id}:${target.id}`
      if (thanked.has(key))
        throw new ApiError('http', 409, 'Вы уже благодарили этого соседа сегодня')
      thanked.add(key)
      target.points += 5
      return profile(target.id)
    },
  ],
  ['POST', /^\/people\/(\d+)\/message$/, () => ({ ok: true })],
  ['GET', /^\/house\/pulse$/, () => pulse()],
  [
    'GET',
    /^\/dev\/users$/,
    () =>
      users.map((u, i) => ({
        ...short(u),
        max_user_id: u.max_user_id,
        role: i === 1 ? 'admin' : 'resident',
      })),
  ],

  [
    'GET',
    /^\/issues$/,
    (_, q) => {
      refreshOverdue()
      return db.issues
        .filter((i) => !q.status || i.status === q.status)
        .filter((i) => matches(q.q, i.title, i.description))
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map(toOut)
    },
  ],
  [
    'POST',
    /^\/issues\/similar$/,
    (_, __, b) => {
      const rule = classifyText(String(b.text ?? ''))
      return db.issues.filter((i) => i.category === rule.code && rule.code !== 'other').map(toOut)
    },
  ],
  ['POST', /^\/issues\/classify$/, (_, __, b) => classification(String(b.text ?? ''))],
  ['GET', /^\/issues\/(\d+)$/, ([id]) => issue(id!)],
  ['POST', /^\/issues\/(\d+)\/vote$/, ([id]) => vote(id!, true)],
  ['DELETE', /^\/issues\/(\d+)\/vote$/, ([id]) => vote(id!, false)],
  [
    'POST',
    /^\/issues\/(\d+)\/status$/,
    ([id], _, b) => {
      const i = issue(id!)
      const status = b.status as IssueDetail['status']
      const title =
        { in_progress: 'В работе', resolved: 'Решено', rejected: 'Отклонено' }[status as string] ??
        status
      Object.assign(i, { status, status_title: title })
      i.timeline.push({
        status,
        status_title: title,
        note: (b.note as string) || null,
        created_at: new Date().toISOString(),
      })
      return i
    },
  ],

  [
    'GET',
    /^\/listings$/,
    (_, q) =>
      db.listings
        .filter((l) =>
          q.scope === 'mine'
            ? l.is_mine
            : q.scope === 'closed'
              ? l.status === 'closed'
              : l.status !== 'closed',
        )
        .filter((l) => !q.category || l.category === q.category)
        .filter((l) => !q.free || l.is_free)
        .filter((l) => matches(q.q, l.title, l.description)),
  ],
  ['GET', /^\/listings\/categories$/, () => null],
  ['GET', /^\/listings\/(\d+)$/, ([id]) => listing(id!)],
  [
    'PATCH',
    /^\/listings\/(\d+)$/,
    ([id], _, b) => Object.assign(listing(id!), { status: b.status }),
  ],
  [
    'DELETE',
    /^\/listings\/(\d+)$/,
    ([id]) => {
      db.listings = db.listings.filter((l) => l.id !== Number(id))
      return undefined
    },
  ],
  ['POST', /^\/listings\/(\d+)\/contact$/, () => ({ ok: true })],

  [
    'GET',
    /^\/events$/,
    (_, q) => {
      const now = Date.now()
      const upcoming = q.scope !== 'past'
      return db.events
        .filter((e) => new Date(e.starts_at).getTime() > now === upcoming)
        .sort((a, b) => (upcoming ? 1 : -1) * a.starts_at.localeCompare(b.starts_at))
        .map(eventOut)
    },
  ],
  [
    'POST',
    /^\/events$/,
    (_, __, b) => {
      const created: EventDetail = {
        id: db.nextId++,
        title: String(b.title),
        description: String(b.description ?? ''),
        kind: b.kind as EventDetail['kind'],
        kind_title: 'Событие',
        starts_at: String(b.starts_at),
        place: String(b.place ?? ''),
        photos: [],
        max_participants: (b.max_participants as number | null) ?? null,
        participants_count: 1,
        joined_by_me: true,
        comments_count: 0,
        author: short(me),
        created_at: new Date().toISOString(),
        score: null,
        participants: [short(me)],
      }
      db.events.push(created)
      return created
    },
  ],
  ['GET', /^\/events\/(\d+)$/, ([id]) => event(id!)],
  [
    'PATCH',
    /^\/events\/(\d+)$/,
    ([id], _, b) => {
      const e = event(id!)
      e.description = String(b.description ?? '').trim()
      return e
    },
  ],
  [
    'DELETE',
    /^\/events\/(\d+)\/photos\/(\d+)$/,
    ([id, index]) => {
      const e = event(id!)
      e.photos = (e.photos ?? []).filter((_, i) => i !== Number(index))
      return e
    },
  ],
  ['POST', /^\/events\/(\d+)\/join$/, ([id]) => join(id!, true)],
  ['DELETE', /^\/events\/(\d+)\/join$/, ([id]) => join(id!, false)],
  ['GET', /^\/events\/(\d+)\/comments$/, ([id]) => db.comments[Number(id)] ?? []],
  [
    'POST',
    /^\/events\/(\d+)\/comments$/,
    ([id], _, b) => {
      const c: CommentOut = {
        id: db.nextId++,
        event_id: Number(id),
        author: short(me),
        text: String(b.text),
        created_at: new Date().toISOString(),
      }
      ;(db.comments[Number(id)] ??= []).push(c)
      event(id!).comments_count += 1
      return c
    },
  ],

  [
    'GET',
    /^\/achievements$/,
    (): AchievementsOut => ({
      items: db.achievements,
      leaderboard: [...users]
        .sort((a, b) => b.points - a.points)
        .map((u, i) => ({
          rank: i + 1,
          user: short(u),
          points: u.points,
          level_title: u.level_title,
          is_me: u.id === me.id,
        })),
    }),
  ],
  ['GET', /^\/shelters$/, () => SHELTERS],
  ['GET', /^\/alerts\/active$/, () => db.alert],
  [
    'POST',
    /^\/alerts$/,
    (_, __, b) =>
      (db.alert = {
        id: db.nextId++,
        kind: 'drone',
        kind_title: 'Беспилотная опасность',
        message: String(b.message ?? ''),
        active: true,
        created_at: new Date().toISOString(),
        ended_at: null,
      }),
  ],
  [
    'POST',
    /^\/alerts\/(\d+)\/end$/,
    () => {
      const ended = { ...db.alert!, active: false, ended_at: new Date().toISOString() }
      db.alert = null
      return ended
    },
  ],

  [
    'GET',
    /^\/search$/,
    (_, q) => ({
      issues: db.issues.filter((i) => matches(q.q, i.title, i.description)).map(toOut),
      events: db.events.filter((e) => matches(q.q, e.title, e.description)).map(eventOut),
      listings: db.listings.filter((l) => matches(q.q, l.title, l.description)),
    }),
  ],
  [
    'POST',
    /^\/assistant\/chat$/,
    (_, __, b) => ({
      reply: `Посмотрел, что происходит в доме. ${pulse().phrase}\n\nВы спросили: «${String(b.message ?? '')}». В демо-режиме я отвечаю заготовкой, но в MAX разберусь по-настоящему.`,
      tools_used: ['get_pulse', 'search_issues'],
    }),
  ],

  ['GET', /^\/mcp\/servers$/, () => MCP_SERVERS],
  [
    'GET',
    /^\/mcp\/servers\/(\d+)\/tools$/,
    () => [
      {
        name: 'house_passport',
        description: 'Паспорт дома: год постройки, этажность, материал стен',
      },
      { name: 'tariffs', description: 'Тарифы ЖКУ для дома' },
      { name: 'capital_repair', description: 'План капремонта по региональной программе' },
    ],
  ],
  [
    'GET',
    /^\/dev\/chats$/,
    () => [{ chat_id: 1, title: 'Ленинского Комсомола, 5 - домовой чат', type: 'chat' }],
  ],
  ['GET', /^\/dev\/chat\/messages$/, () => []],
]

export async function mockRequest<T>(
  method: string,
  path: string,
  query: Query = {},
  body: Body = {},
): Promise<T> {
  await sleep(scenario.latency)
  syncMe()
  if (scenario.name === 'boot-error')
    throw new ApiError('network', 0, 'Нет связи с сервером. Проверьте интернет')
  if (scenario.name === 'error' && path !== '/me') {
    throw new ApiError('http', 500, 'Кузя споткнулся на сервере. Попробуйте ещё раз')
  }
  for (const [m, re, handler] of routes) {
    if (m !== method) continue
    const found = path.match(re)
    if (!found) continue
    const result = handler(found.slice(1), query, body)
    // Отдаём копию, как настоящая сеть: сторы не должны делить объекты с «базой»
    return (result === undefined ? undefined : structuredClone(result)) as T
  }
  console.warn('[mock] нет обработчика', method, path)
  return { ok: true } as T
}

/** multipart-загрузка: поля FormData и фото как object URL. */
export async function mockUpload<T>(
  path: string,
  form: FormData,
  onProgress?: (f: number) => void,
): Promise<T> {
  syncMe()
  for (const f of [0.3, 0.7, 1]) {
    await sleep(scenario.latency / 2)
    onProgress?.(f)
  }
  const photos = form
    .getAll('photos')
    .filter((p): p is File => p instanceof File)
    .map((f) => URL.createObjectURL(f))
  const text = String(form.get('description') ?? '')
  if (path === '/issues') {
    const rule = classifyText(text)
    const created = buildIssue(
      {
        id: db.nextId++,
        title: String(form.get('title') ?? '') || rule.title,
        description: text,
        category: rule.code,
        status: 'voting',
        author: me.id,
        votes: 1,
        votedByMe: true,
        createdAgo: 0,
        photos,
        location: String(form.get('location_hint') ?? '') || undefined,
      },
      users,
      needed,
    )
    db.issues.unshift(created)
    return structuredClone(created) as T
  }
  if (path === '/me/avatar/photo') {
    const file = form.get('photo')
    if (!(file instanceof File)) throw new ApiError('http', 422, 'Выберите фото')
    me.avatar = 'upload'
    me.photo_url = URL.createObjectURL(file)
    return meOut() as T
  }
  if (path === '/documents') {
    const file = form.get('file')
    const scope = form.get('scope') === 'house' ? 'house' : 'personal'
    if (scope === 'house' && scenario.role !== 'admin')
      throw new ApiError('http', 403, 'Документы дома загружает администратор')
    const created: DocumentOut = {
      id: db.nextId++,
      title: String(form.get('title') ?? ''),
      filename: file instanceof File ? file.name : 'document',
      content_type: file instanceof File ? file.type : 'application/octet-stream',
      size: file instanceof File ? file.size : 0,
      scope,
      author: short(me),
      can_delete: true,
      created_at: new Date().toISOString(),
    }
    db.documents.unshift(created)
    return structuredClone(created) as T
  }
  const eventPhotos = path.match(/^\/events\/(\d+)\/photos$/)
  if (eventPhotos) {
    const e = event(eventPhotos[1]!)
    e.photos = [...(e.photos ?? []), ...photos].slice(0, 5)
    return structuredClone(e) as T
  }
  if (path === '/listings') {
    const price = Number(form.get('price') ?? 0)
    const category = String(form.get('category') ?? 'other')
    const created: ListingOut = {
      id: db.nextId++,
      title: String(form.get('title') ?? ''),
      description: text,
      price,
      is_free: price === 0,
      category,
      category_title: LISTING_CATEGORY_TITLES[category] ?? 'Разное',
      status: 'active',
      photos,
      author: short(me),
      is_mine: true,
      created_at: new Date().toISOString(),
      score: null,
    }
    db.listings.unshift(created)
    return structuredClone(created) as T
  }
  return mockRequest<T>('POST', path)
}
