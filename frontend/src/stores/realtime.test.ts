/**
 * Сторы и события реального времени: настоящий поток SSE (фейковый EventSource)
 * и настоящий API-клиент поверх подменённого fetch, без мок-бэкенда.
 */
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import type {
  AnnouncementOut,
  ChatMessage,
  CommentOut,
  EventDetail,
  IssueDetail,
  ListingOut,
  MeOut,
  PulseOut,
} from '@/api/types'
import { FakeEventSource } from '@/test/fakeEventSource'

vi.mock('@/api/mode', () => ({
  MOCK_API: false,
  BROWSER_DEMO: false,
  startBrowserDemo: vi.fn(),
  stopBrowserDemo: vi.fn(),
}))

const AUTHOR = { id: 3, first_name: 'Марина', last_name: 'Соколова' }
const ME = { id: 1, first_name: 'Анна', last_name: 'Петрова' }

function issue(id: number, patch: Partial<IssueDetail> = {}): IssueDetail {
  return {
    id,
    title: `Заявка ${id}`,
    description: 'Описание',
    category: 'roof',
    category_title: 'Крыша',
    status: 'voting',
    status_title: 'Голосование',
    votes_count: 2,
    votes_needed: 6,
    voted_by_me: false,
    photos: [],
    author: AUTHOR,
    responsible_org: null,
    created_at: '2026-10-20T10:00:00Z',
    sent_at: null,
    deadline_at: null,
    is_overdue: false,
    score: null,
    legal_basis: null,
    deadline_hours: null,
    appeal_text: null,
    location_hint: null,
    timeline: [],
    ...patch,
  }
}

function event(id: number, patch: Partial<EventDetail> = {}): EventDetail {
  return {
    id,
    title: `Событие ${id}`,
    description: '',
    kind: 'subbotnik',
    kind_title: 'Субботник',
    starts_at: '2030-05-01T07:00:00Z',
    place: 'Двор',
    max_participants: null,
    participants_count: 1,
    joined_by_me: false,
    comments_count: 0,
    author: AUTHOR,
    created_at: '2026-10-20T10:00:00Z',
    participants: [AUTHOR],
    ...patch,
  }
}

function listing(id: number, patch: Partial<ListingOut> = {}): ListingOut {
  return {
    id,
    title: `Вещь ${id}`,
    description: '',
    price: 0,
    is_free: true,
    category: 'kids',
    category_title: 'Детское',
    status: 'active',
    photos: [],
    author: AUTHOR,
    is_mine: false,
    created_at: '2026-10-20T10:00:00Z',
    ...patch,
  }
}

function announcement(id: number, patch: Partial<AnnouncementOut> = {}): AnnouncementOut {
  return {
    id,
    title: `Объявление ${id}`,
    text: '',
    pinned: false,
    event_id: null,
    author: null,
    is_mine: false,
    created_at: '2026-10-20T10:00:00Z',
    ...patch,
  }
}

function message(id: string, text: string): ChatMessage {
  return {
    id,
    chat_id: 1,
    from: { user_id: 1001, name: 'Анна' },
    text,
    buttons: null,
    deleted: false,
    notice: null,
    created_at: '2026-10-20T10:00:00Z',
  }
}

const PULSE: PulseOut = {
  mood: 'ok',
  score: 70,
  level: 3,
  xp: 340,
  xp_next: 500,
  phrase: 'Всё спокойно',
  stats: {
    open_issues: 1,
    overdue_issues: 0,
    resolved_30d: 0,
    upcoming_events: 0,
    active_listings: 0,
    active_alert: false,
  },
}

const ME_OUT = {
  user: { ...ME, max_user_id: 1001, points: 150, level: 3, level_title: 'Добрый сосед' },
  house: { id: 1, title: 'Дом', address: '', lat: 54.3, lon: 48.4 },
  role: 'resident',
  mock: false,
} as MeOut

/** Ответы «сервера» по пути запроса; чего нет - пустой список. */
let responses: Record<string, unknown>
let fetchMock: Mock
let haptic: Mock

function requested(path: string): boolean {
  return fetchMock.mock.calls.some(([url]) => String(url).startsWith(`/api/v1${path}`))
}

async function flush(): Promise<void> {
  for (let i = 0; i < 4; i++) await new Promise((resolve) => setTimeout(resolve, 0))
}

beforeEach(() => {
  vi.resetModules()
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  responses = {}
  fetchMock = vi.fn(async (url: string) => {
    const path = String(url).replace('/api/v1', '').split('?')[0]!
    const body = path in responses ? responses[path] : []
    return new Response(JSON.stringify(body), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  haptic = vi.fn()
  window.WebApp = {
    initData: 'signed-init',
    platform: 'ios',
    HapticFeedback: { impactOccurred: vi.fn(), notificationOccurred: haptic },
  }
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.useRealTimers()
  delete window.WebApp
})

/** Свежие модули (обработчики событий регистрируются заново) и открытый поток. */
async function connect() {
  const sse = await import('@/realtime/sse')
  const { notify } = await import('@/lib/notify')
  const stores = {
    issues: (await import('./issues')).useIssuesStore(),
    events: (await import('./events')).useEventsStore(),
    listings: (await import('./listings')).useListingsStore(),
    announcements: (await import('./announcements')).useAnnouncementsStore(),
    pulse: (await import('./pulse')).usePulseStore(),
    alerts: (await import('./alerts')).useAlertsStore(),
    session: (await import('./session')).useSessionStore(),
    chat: (await import('./chat')).useDevChatStore(),
  }
  sse.connectRealtime()
  const es = FakeEventSource.last()
  es.open()
  return { sse, es, notify, ...stores }
}

describe('заявки в реальном времени', () => {
  it('новая заявка соседа появляется сверху загруженного списка', async () => {
    const { es, issues } = await connect()
    issues.items = [issue(101)]
    issues.loaded = true
    es.emit('issue.created', issue(110))
    expect(issues.items.map((i) => i.id)).toEqual([110, 101])
  })

  it('пока список не загружен или заявка не подходит под фильтр, её не добавляет', async () => {
    const { es, issues } = await connect()
    es.emit('issue.created', issue(110))
    expect(issues.items).toEqual([])
    issues.loaded = true
    issues.status = 'resolved'
    es.emit('issue.created', issue(111))
    es.emit('issue.created', { title: 'без id' })
    expect(issues.items).toEqual([])
  })

  it('обновление заявки не трогает голос этого жителя', async () => {
    const { es, issues } = await connect()
    issues.items = [issue(101, { voted_by_me: true, votes_count: 3 })]
    issues.loaded = true
    es.emit('issue.updated', issue(101, { voted_by_me: false, votes_count: 4 }))
    expect(issues.items[0]).toMatchObject({ voted_by_me: true, votes_count: 4 })
  })

  it('заявка, ушедшая из фильтра, пропадает из списка', async () => {
    const { es, issues } = await connect()
    issues.items = [issue(101)]
    issues.loaded = true
    issues.status = 'voting'
    es.emit('issue.updated', issue(101, { status: 'sent' }))
    expect(issues.items).toEqual([])
  })

  it('открытая карточка обновляется и дозапрашивает историю', async () => {
    const { es, issues } = await connect()
    issues.details = { 101: issue(101, { voted_by_me: true }) }
    responses['/issues/101'] = issue(101, {
      status: 'sent',
      voted_by_me: true,
      timeline: [
        { status: 'sent', status_title: 'Отправлено', note: null, created_at: '2026-10-21' },
      ],
    })
    es.emit('issue.updated', issue(101, { status: 'sent', voted_by_me: false }))
    expect(issues.details[101]).toMatchObject({ status: 'sent', voted_by_me: true })
    await flush()
    expect(requested('/issues/101')).toBe(true)
    expect(issues.details[101]?.timeline).toHaveLength(1)
  })
})

describe('пульс, тревога и награды', () => {
  it('полный пульс из события заменяет текущий', async () => {
    const { es, pulse } = await connect()
    es.emit('pulse.changed', { ...PULSE, mood: 'sad' })
    expect(pulse.pulse?.mood).toBe('sad')
  })

  it('неполное событие пульса: тихий перезапрос через паузу', async () => {
    const { es, pulse } = await connect()
    pulse.pulse = PULSE
    responses['/house/pulse'] = { ...PULSE, score: 40 }
    vi.useFakeTimers()
    es.emit('pulse.changed', { changed: true })
    es.emit('issue.created', issue(120))
    await vi.advanceTimersByTimeAsync(400)
    vi.useRealTimers()
    await flush()
    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/house/pulse'))).toHaveLength(1)
    expect(pulse.pulse?.score).toBe(40)
  })

  it('тревога из события: экран тревоги и вибрация', async () => {
    const { es, alerts } = await connect()
    es.emit('alert.started', {
      id: 9,
      kind: 'drone',
      kind_title: 'Беспилотная опасность',
      message: 'Отойдите от окон',
      active: true,
      created_at: '2026-10-21T06:00:00Z',
      ended_at: null,
    })
    expect(alerts.active?.message).toBe('Отойдите от окон')
    expect(haptic).toHaveBeenCalledWith('warning')
    await flush()
    expect(requested('/shelters')).toBe(true)
  })

  it('тревога без данных: стор сам спрашивает активную тревогу', async () => {
    const { es } = await connect()
    responses['/alerts/active'] = null
    es.emit('alert.started', {})
    await flush()
    expect(requested('/alerts/active')).toBe(true)
  })

  it('отбой тревоги закрывает экран и сообщает жителю', async () => {
    const { es, alerts, notify } = await connect()
    const success = vi.spyOn(notify, 'success')
    es.emit('alert.started', { id: 9, kind: 'drone', active: true })
    es.emit('alert.ended', { id: 9 })
    expect(alerts.active).toBeNull()
    expect(success).toHaveBeenCalledWith(
      'Отбой тревоги',
      'Опасность миновала. Можно возвращаться домой',
    )
  })

  it('награда жителю: поздравление и обновлённые очки', async () => {
    const { es, session, notify } = await connect()
    const success = vi.spyOn(notify, 'success')
    responses['/me'] = ME_OUT
    window.WebApp = { initData: 'signed-init', platform: 'ios' }
    await session.init()
    fetchMock.mockClear()
    es.emit('achievement.awarded', { user_id: 1, title: 'Первая заявка', points: 10 })
    expect(success).toHaveBeenCalledWith('Новая награда: Первая заявка', '+10 очков')
    await flush()
    expect(requested('/me')).toBe(true)

    es.emit('achievement.awarded', { user_id: 1 })
    expect(success).toHaveBeenLastCalledWith(
      'Новая награда!',
      'Загляните в раздел «Награды и рейтинг»',
    )
    es.emit('achievement.awarded', { user_id: 2, title: 'Чужая' })
    expect(success).toHaveBeenCalledTimes(2)
  })
})

describe('события, вещи, объявления и чат', () => {
  it('новое событие в будущем встаёт в список по дате, прошедшее - нет', async () => {
    const { es, events } = await connect()
    events.scopes = {
      upcoming: {
        items: [event(301, { starts_at: '2030-06-01T07:00:00Z' })],
        loaded: true,
        loading: false,
        error: null,
      },
      past: { items: [], loaded: false, loading: false, error: null },
    }
    es.emit('event.created', event(310, { starts_at: '2030-05-01T07:00:00Z' }))
    es.emit('event.created', event(311, { starts_at: '2001-01-01T07:00:00Z' }))
    expect(events.scopes.upcoming.items.map((e) => e.id)).toEqual([310, 301])
  })

  it('обновление события сохраняет «Иду» жителя и дозапрашивает участников', async () => {
    const { es, events } = await connect()
    events.scopes = {
      upcoming: {
        items: [event(301, { joined_by_me: true })],
        loaded: true,
        loading: false,
        error: null,
      },
      past: { items: [], loaded: false, loading: false, error: null },
    }
    events.details = { 301: event(301, { joined_by_me: true }) }
    responses['/events/301'] = event(301, { joined_by_me: true, participants_count: 7 })
    es.emit('event.updated', event(301, { joined_by_me: false, participants_count: 7 }))
    expect(events.scopes.upcoming.items[0]).toMatchObject({
      joined_by_me: true,
      participants_count: 7,
    })
    expect(events.details[301]?.joined_by_me).toBe(true)
    await flush()
    expect(requested('/events/301')).toBe(true)
  })

  it('комментарий соседа дописывается в открытое обсуждение один раз', async () => {
    const { es, events } = await connect()
    const comment: CommentOut = {
      id: 77,
      event_id: 301,
      author: AUTHOR,
      text: 'Возьму краску',
      created_at: '2026-10-21T06:00:00Z',
    }
    events.comments = { 301: [] }
    es.emit('comment.created', comment)
    es.emit('comment.created', comment)
    es.emit('comment.created', { id: 78, text: 'без события' })
    expect(events.comments[301]).toHaveLength(1)
  })

  it('новая вещь соседа появляется сверху, своя помечается моей', async () => {
    const { es, listings, session } = await connect()
    session.me = ME_OUT
    listings.loaded = true
    listings.items = [listing(201)]
    es.emit('listing.created', listing(210, { author: ME }))
    expect(listings.items[0]).toMatchObject({ id: 210, is_mine: true })
  })

  it('удалённая автором вещь пропадает из списка и кэша', async () => {
    const { es, listings } = await connect()
    listings.items = [listing(201), listing(202)]
    listings.details = { 201: listing(201) }
    es.emit('listing.updated', { id: 201, deleted: true })
    expect(listings.items.map((l) => l.id)).toEqual([202])
    expect(listings.details[201]).toBeUndefined()
  })

  it('закрытая вещь уходит из открытых, изменённая обновляется', async () => {
    const { es, listings } = await connect()
    listings.items = [listing(201), listing(202)]
    listings.details = { 202: listing(202) }
    es.emit('listing.updated', listing(201, { status: 'closed' }))
    es.emit('listing.updated', listing(202, { title: 'Коляска, торг' }))
    expect(listings.items.map((l) => l.title)).toEqual(['Коляска, торг'])
    expect(listings.details[202]?.title).toBe('Коляска, торг')
  })

  it('объявления: новое встаёт по порядку, удалённое пропадает', async () => {
    const { es, announcements } = await connect()
    announcements.loaded = true
    announcements.items = [announcement(901, { pinned: true })]
    const fresh = { created_at: '2026-10-21T06:00:00Z' }
    es.emit('announcement.created', announcement(905, fresh))
    expect(announcements.items.map((a) => a.id)).toEqual([901, 905])
    es.emit('announcement.updated', announcement(905, { ...fresh, pinned: true, title: 'Важно' }))
    expect(announcements.items[0]?.title).toBe('Важно')
    es.emit('announcement.updated', { id: 901, deleted: true })
    expect(announcements.items.map((a) => a.id)).toEqual([905])
  })

  it('чат: новое сообщение дописывается, правка заменяет старое', async () => {
    const { es, chat } = await connect()
    chat.messages = { 1: [message('a', 'Привет')] }
    es.emit('chat.message', message('b', 'Кто дома?'))
    es.emit('chat.message', { ...message('a', ''), deleted: true })
    es.emit('chat.message', { ...message('c', 'в чужой чат'), chat_id: 5 })
    es.emit('chat.message', { text: 'без id' })
    expect(chat.messages[1]?.map((m) => m.id)).toEqual(['a', 'b'])
    expect(chat.messages[1]?.[0]?.deleted).toBe(true)
    expect(chat.messages[5]).toBeUndefined()
  })

  it('ответ бота на кнопку показывается всплывашкой', async () => {
    const { es, notify } = await connect()
    const info = vi.spyOn(notify, 'info')
    es.emit('chat.notice', { callback_id: 'x', text: 'Голос учтён' })
    es.emit('chat.notice', null)
    expect(info).toHaveBeenCalledTimes(1)
    expect(info).toHaveBeenCalledWith('Голос учтён')
  })
})

describe('после обрыва связи', () => {
  it('загруженные списки добирают пропущенное', async () => {
    const { sse, issues, events, listings, announcements, alerts, chat } = await connect()
    issues.loaded = true
    events.scopes = {
      upcoming: { items: [], loaded: true, loading: false, error: null },
      past: { items: [], loaded: false, loading: false, error: null },
    }
    events.comments = { 301: [] }
    listings.loaded = true
    announcements.loaded = true
    chat.currentChatId = 1
    chat.messages = { 1: [] }
    void alerts
    fetchMock.mockClear()

    // новое подключение после уже бывшего: поток шлёт resync
    sse.connectRealtime()
    FakeEventSource.last().open()
    await flush()
    for (const path of [
      '/issues',
      '/events',
      '/events/301/comments',
      '/listings',
      '/announcements',
      '/alerts/active',
      '/dev/chat/messages',
    ]) {
      expect(requested(path), path).toBe(true)
    }
  })
})
