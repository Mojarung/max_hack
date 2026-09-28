/**
 * Демо-данные мок-режима: панельная девятиэтажка в Ульяновске (Новый Город).
 * Всё строится от текущего времени, чтобы таймеры сроков и даты событий выглядели живыми.
 */
import type {
  AchievementOut,
  AlertOut,
  CommentOut,
  EventDetail,
  House,
  IssueDetail,
  IssueStatus,
  ListingOut,
  McpServerOut,
  ShelterOut,
  UserFull,
  UserShort,
} from '@/api/types'
import type { MockScenario } from './scenario'

const H = 3_600_000
const D = 24 * H
const at = (ms: number) => new Date(Date.now() + ms).toISOString()
/** Дата события: через `days` дней в `hour`:00. */
const dayAt = (days: number, hour: number) => {
  const d = new Date(Date.now() + days * D)
  d.setHours(hour, 0, 0, 0)
  return d.toISOString()
}

/** Фото для демо из public/demo (Unsplash, источники в public/demo/CREDITS.md). */
export function photo(name: string): string {
  return `${import.meta.env.BASE_URL}demo/${name}.jpg`
}

export const HOUSE: House = {
  id: 1,
  title: 'Ленинского Комсомола, 5',
  address: 'Ульяновск, пр-т Ленинского Комсомола, 5',
  lat: 54.3857,
  lon: 48.6072,
  members_count: 40,
  vote_threshold_pct: 15,
  uk_name: 'УК «Уютный дом»',
}

export function buildUsers(s: MockScenario): UserFull[] {
  const base = (u: Partial<UserFull> & Pick<UserFull, 'id' | 'first_name'>): UserFull => ({
    max_user_id: 1000 + u.id,
    last_name: null,
    photo_url: null,
    apartment: null,
    username: null,
    points: 0,
    level: 1,
    level_title: 'Новосёл',
    next_level_points: 50,
    ...u,
  })
  return [
    base({
      id: 1,
      first_name: s.name === 'long' ? 'Констанция' : 'Анна',
      last_name: s.name === 'long' ? 'Константинопольская-Задунайская' : 'Петрова',
      apartment: '12',
      points: s.name === 'empty' ? 0 : 145,
      level: s.name === 'empty' ? 1 : 3,
      level_title: s.name === 'empty' ? 'Новосёл' : 'Добрый сосед',
      next_level_points: s.name === 'empty' ? 50 : 250,
    }),
    base({
      id: 2,
      first_name: 'Ильдар',
      last_name: 'Хайруллин',
      apartment: '45',
      points: 420,
      level: 5,
      level_title: 'Хранитель дома',
      next_level_points: 600,
    }),
    base({
      id: 3,
      first_name: 'Марина',
      last_name: 'Соколова',
      apartment: '7',
      points: 210,
      level: 3,
    }),
    base({
      id: 4,
      first_name: 'Рустем',
      last_name: 'Галиев',
      apartment: '88',
      points: 95,
      level: 2,
    }),
    base({
      id: 5,
      first_name: 'Ольга',
      last_name: 'Смирнова',
      apartment: '23',
      points: 60,
      level: 2,
    }),
    base({ id: 6, first_name: 'Тимур', last_name: 'Зарипов', apartment: '101', points: 30 }),
  ]
}

export function short(u: UserFull): UserShort {
  return {
    id: u.id,
    max_user_id: u.max_user_id,
    first_name: u.first_name,
    last_name: u.last_name,
    photo_url: u.photo_url,
    apartment: u.apartment,
  }
}

const STATUS_TITLES: Record<IssueStatus, string> = {
  voting: 'Голосование',
  sent: 'Отправлено',
  in_progress: 'В работе',
  resolved: 'Решено',
  rejected: 'Отклонено',
}

export interface CategoryRule {
  code: string
  title: string
  words: string[]
  org: { name: string; kind: string; kind_title: string }
  basis: string
  hours: number
}

const UK = { name: 'УК «Уютный дом»', kind: 'uk', kind_title: 'Управляющая компания' }
const TKO = {
  name: 'Регоператор ТКО «Гринта»',
  kind: 'tko',
  kind_title: 'Региональный оператор ТКО',
}
const CITY = {
  name: 'Администрация Ново-Савиновского района',
  kind: 'city',
  kind_title: 'Администрация района',
}

export const CATEGORIES: CategoryRule[] = [
  {
    code: 'roof',
    title: 'Кровля',
    words: ['крыш', 'кровл', 'протека', 'теч'],
    org: UK,
    basis: 'Постановление Госстроя № 170, прил. 2',
    hours: 24,
  },
  {
    code: 'elevator',
    title: 'Лифт',
    words: ['лифт'],
    org: UK,
    basis: 'ПП РФ № 290, п. 22',
    hours: 24,
  },
  {
    code: 'water',
    title: 'Водоснабжение',
    words: ['вод', 'кран'],
    org: UK,
    basis: 'ПП РФ № 354, прил. 1',
    hours: 24,
  },
  {
    code: 'heating',
    title: 'Отопление',
    words: ['отоплен', 'батаре', 'холодн'],
    org: UK,
    basis: 'ПП РФ № 354, прил. 1, п. 15',
    hours: 24,
  },
  {
    code: 'lighting',
    title: 'Освещение',
    words: ['свет', 'ламп', 'темно'],
    org: UK,
    basis: 'Постановление Госстроя № 170, п. 5.6',
    hours: 168,
  },
  {
    code: 'garbage',
    title: 'Вывоз мусора',
    words: ['мусор', 'бак', 'контейнер'],
    org: TKO,
    basis: 'ПП РФ № 354, прил. 1, п. 17',
    hours: 24,
  },
  {
    code: 'yard',
    title: 'Двор',
    words: ['двор', 'лавочк', 'площадк', 'дерев'],
    org: UK,
    basis: 'ПП РФ № 290, п. 25',
    hours: 120,
  },
  {
    code: 'road',
    title: 'Дорога и тротуар',
    words: ['ям', 'дорог', 'асфальт', 'тротуар'],
    org: CITY,
    basis: '131-ФЗ, ст. 16',
    hours: 720,
  },
  { code: 'other', title: 'Другое', words: [], org: UK, basis: '59-ФЗ, ст. 12', hours: 720 },
]

export function classifyText(text: string): CategoryRule {
  const lower = text.toLowerCase()
  return CATEGORIES.find((c) => c.words.some((w) => lower.includes(w))) ?? CATEGORIES.at(-1)!
}

interface IssueSeed {
  id: number
  title: string
  description: string
  category: string
  status: IssueStatus
  author: number
  votes: number
  votedByMe?: boolean
  createdAgo: number
  sentAgo?: number
  deadlineIn?: number
  photos?: string[]
  location?: string
  notes?: Partial<Record<IssueStatus, string>>
}

export function buildIssue(seed: IssueSeed, users: UserFull[], needed: number): IssueDetail {
  const rule = CATEGORIES.find((c) => c.code === seed.category) ?? CATEGORIES.at(-1)!
  const author = users.find((u) => u.id === seed.author) ?? users[0]!
  const sent = seed.sentAgo !== undefined ? at(-seed.sentAgo) : null
  const deadline = seed.deadlineIn !== undefined ? at(seed.deadlineIn) : null
  const path: IssueStatus[] =
    seed.status === 'voting'
      ? ['voting']
      : seed.status === 'sent'
        ? ['voting', 'sent']
        : ['voting', 'sent', seed.status]
  const stamps = [seed.createdAgo, seed.sentAgo ?? 0, (seed.sentAgo ?? 0) / 2]
  const timeline = path.map((status, i) => ({
    status,
    status_title: STATUS_TITLES[status],
    note:
      seed.notes?.[status] ??
      (status === 'voting'
        ? 'Кузя опубликовал проблему в домовом чате'
        : status === 'sent'
          ? `Обращение отправлено: ${rule.org.name}`
          : null),
    created_at: at(-stamps[i]!),
  }))
  return {
    id: seed.id,
    title: seed.title,
    description: seed.description,
    category: rule.code,
    category_title: rule.title,
    status: seed.status,
    status_title: STATUS_TITLES[seed.status],
    votes_count: seed.votes,
    votes_needed: needed,
    voted_by_me: !!seed.votedByMe,
    photos: seed.photos ?? [],
    author: short(author),
    responsible_org: rule.org,
    created_at: at(-seed.createdAgo),
    sent_at: sent,
    deadline_at: deadline,
    is_overdue:
      !!deadline &&
      new Date(deadline).getTime() < Date.now() &&
      ['sent', 'in_progress'].includes(seed.status),
    score: null,
    legal_basis: rule.basis,
    deadline_hours: rule.hours,
    appeal_text:
      seed.status === 'voting'
        ? null
        : `${rule.org.name}\nот жителей дома по адресу: ${HOUSE.address}\n\nОБРАЩЕНИЕ\n\n${seed.description}\n\nПросим устранить неисправность в срок, установленный нормативом (${rule.hours} ч): ${rule.basis}.\n\nОбращение поддержали ${seed.votes} жителей дома.\nОтвет просим направить в домовой чат MAX.`,
    location_hint: seed.location ?? null,
    timeline,
  }
}

export function buildIssues(s: MockScenario, users: UserFull[], needed: number): IssueDetail[] {
  if (s.name === 'empty') return []
  const long =
    s.name === 'long'
      ? ' В подъезде номер два на лестничной площадке между восьмым и девятым этажом'
      : ''
  const seeds: IssueSeed[] = [
    {
      id: 101,
      title: `Течёт крыша над 9 этажом${long}`,
      description:
        'Во втором подъезде после дождя течёт с потолка на лестничную клетку 9 этажа. Вода капает на ступени, скользко. На потолке пятно и отходит штукатурка.',
      category: 'roof',
      status: 'voting',
      author: 3,
      votes: needed - 2,
      createdAgo: 5 * H,
      photos: [photo('roof-drip'), photo('roof-stain')],
      location: 'Подъезд 2, 9 этаж',
    },
    {
      id: 102,
      title: 'Не горит свет в подъезде 3',
      description:
        'Третий день не горят лампы на 1-4 этажах третьего подъезда. Вечером темно, пожилым жителям страшно спускаться.',
      category: 'lighting',
      status: 'voting',
      author: 5,
      votes: 2,
      votedByMe: true,
      createdAgo: 30 * H,
      location: 'Подъезд 3, 1-4 этажи',
    },
    {
      id: 103,
      title: 'Не работает лифт в подъезде 1',
      description: 'Лифт стоит на 5 этаже с открытыми дверями, на кнопки не реагирует.',
      category: 'elevator',
      status: 'sent',
      author: 2,
      votes: needed + 1,
      createdAgo: 10 * H,
      sentAgo: 6 * H,
      deadlineIn: s.name === 'overdue' ? -9 * H : 18 * H,
      photos: [photo('elevator')],
    },
    {
      id: 104,
      title: 'Нет горячей воды',
      description: 'Во всём доме с утра нет горячей воды, объявлений об отключении не было.',
      category: 'water',
      status: 'in_progress',
      author: 4,
      votes: needed + 5,
      createdAgo: 26 * H,
      sentAgo: 22 * H,
      deadlineIn: s.name === 'overdue' ? -30 * H : 2 * H,
      notes: { in_progress: 'УК: бригада на месте, меняют задвижку в подвале' },
    },
    {
      id: 105,
      title: 'Переполнены мусорные баки',
      description:
        'Контейнерная площадка у 1 подъезда переполнена, мусор лежит на земле. Вывоза не было с пятницы.',
      category: 'garbage',
      status: 'sent',
      author: 1,
      votes: needed,
      createdAgo: 3 * D,
      sentAgo: 44 * H,
      deadlineIn: -20 * H,
      photos: [photo('garbage')],
    },
    {
      id: 106,
      title: 'Сломана лавочка у 3 подъезда',
      description: 'У лавочки отломана доска сиденья, торчат гвозди.',
      category: 'yard',
      status: 'resolved',
      author: 6,
      votes: needed,
      createdAgo: 9 * D,
      sentAgo: 8 * D,
      notes: { resolved: 'Доску заменили, гвозди убрали' },
    },
    {
      id: 107,
      title: 'Яма на въезде во двор',
      description: 'На въезде во двор со стороны проспекта глубокая яма, машины бьют подвеску.',
      category: 'road',
      status: 'rejected',
      author: 4,
      votes: needed,
      createdAgo: 20 * D,
      sentAgo: 19 * D,
      notes: { rejected: 'Администрация: ремонт включён в план на следующий год' },
    },
  ]
  if (s.name === 'overdue') {
    seeds.push({
      id: 108,
      title: 'Холодные батареи в квартирах 1-20',
      description: 'Отопление дали, но в стояке первого подъезда батареи еле тёплые.',
      category: 'heating',
      status: 'in_progress',
      author: 2,
      votes: needed + 3,
      createdAgo: 5 * D,
      sentAgo: 4 * D,
      deadlineIn: -3 * D,
    })
  }
  return seeds.map((seed) => buildIssue(seed, users, needed))
}

export function buildListings(s: MockScenario, users: UserFull[], meId: number): ListingOut[] {
  if (s.name === 'empty') return []
  const titles: Record<string, string> = {
    furniture: 'Мебель',
    kids: 'Детское',
    plants: 'Растения',
    tools: 'Инструменты',
    electronics: 'Техника',
    services: 'Услуги',
  }
  const rows: [number, string, string, number, string, ListingOut['status'], number, string?][] = [
    [
      201,
      'Детская коляска 2 в 1',
      'Коляска после одного ребёнка, всё работает, есть дождевик.',
      0,
      'kids',
      'active',
      3,
      photo('stroller'),
    ],
    [
      202,
      s.name === 'long'
        ? 'Диван-книжка раскладной, велюр, серо-голубой, почти не пользовались, самовывоз с 5 этажа'
        : 'Диван-книжка',
      'Раскладной, чистый, без пятен. Самовывоз, 5 этаж, лифт есть.',
      3500,
      'furniture',
      'active',
      4,
      photo('sofa'),
    ],
    [
      203,
      'Рассада томатов',
      'Черри и бычье сердце, 20 кустов. Отдам соседям.',
      0,
      'plants',
      'active',
      5,
      photo('seedlings'),
    ],
    [
      204,
      'Шуруповёрт Makita',
      'С двумя аккумуляторами и набором свёрл. Можно взять на выходные.',
      1500,
      'tools',
      'reserved',
      2,
      photo('drill'),
    ],
    [
      205,
      'Телевизор Samsung 32"',
      'Рабочий, пульт в комплекте.',
      4000,
      'electronics',
      'active',
      meId,
    ],
    [
      206,
      'Помогу настроить телефон',
      'Установлю MAX, Госуслуги, настрою крупный шрифт. Для пожилых соседей бесплатно.',
      0,
      'services',
      'active',
      6,
    ],
  ]
  return rows.map(([id, title, description, price, category, status, authorId, pic], i) => ({
    id,
    title,
    description,
    price,
    is_free: price === 0,
    category,
    category_title: titles[category] ?? 'Разное',
    status,
    photos: pic ? [pic] : [],
    author: short(users.find((u) => u.id === authorId) ?? users[0]!),
    is_mine: authorId === meId,
    created_at: at(-(i + 1) * 7 * H),
    score: null,
  }))
}

export function buildEvents(s: MockScenario, users: UserFull[]): EventDetail[] {
  if (s.name === 'empty') return []
  const pick = (...ids: number[]) => ids.map((id) => short(users.find((u) => u.id === id)!))
  const ev = (
    id: number,
    title: string,
    description: string,
    kind: EventDetail['kind'],
    starts_at: string,
    place: string,
    participants: UserShort[],
    max: number | null,
    comments: number,
  ): EventDetail => ({
    id,
    title,
    description,
    kind,
    kind_title: {
      subbotnik: 'Субботник',
      meeting: 'Собрание',
      holiday: 'Праздник',
      sport: 'Спорт',
      kids: 'Для детей',
      other: 'Другое',
    }[kind],
    starts_at,
    place,
    max_participants: max,
    participants_count: participants.length,
    joined_by_me: participants.some((p) => p.id === 1),
    comments_count: comments,
    author: participants[0] ?? short(users[1]!),
    created_at: at(-3 * D),
    score: null,
    participants,
  })
  return [
    ev(
      301,
      'Осенний субботник',
      'Сгребаем листья, красим лавочки и бордюры. Перчатки и грабли выдаст УК, чай с пирогами - за Мариной.',
      'subbotnik',
      dayAt(3, 10),
      'Двор, у детской площадки',
      pick(3, 2, 4, 5),
      20,
      4,
    ),
    ev(
      302,
      s.name === 'long'
        ? 'Общее собрание собственников по вопросу капитального ремонта кровли и замены лифтового оборудования'
        : 'Собрание по капремонту кровли',
      'Обсуждаем смету и сроки капремонта кровли, голосуем за подрядчика.',
      'meeting',
      dayAt(6, 19),
      'Холл 1 подъезда',
      pick(2, 1),
      null,
      2,
    ),
    ev(
      303,
      'Праздник двора',
      'Музыка, конкурсы для детей, чаепитие. Приносите настольные игры!',
      'holiday',
      dayAt(12, 15),
      'Двор',
      pick(6),
      null,
      0,
    ),
    ev(
      304,
      'Турнир по мини-футболу',
      'Дом на дом: Ленинского Комсомола, 5 против дома 7.',
      'sport',
      dayAt(-8, 11),
      'Спортплощадка школы № 39',
      pick(4, 6, 1),
      12,
      6,
    ),
    ev(
      305,
      'Весенний субботник',
      'Посадили 6 кустов сирени у второго подъезда.',
      'subbotnik',
      dayAt(-160, 10),
      'Двор',
      pick(3, 5),
      null,
      3,
    ),
  ]
}

export function buildComments(users: UserFull[]): Record<number, CommentOut[]> {
  const c = (
    id: number,
    event_id: number,
    userId: number,
    text: string,
    ago: number,
  ): CommentOut => ({
    id,
    event_id,
    author: short(users.find((u) => u.id === userId)!),
    text,
    created_at: at(-ago),
  })
  return {
    301: [
      c(1, 301, 2, 'Грабли и мешки УК привезёт к 9:45', 20 * H),
      c(2, 301, 3, 'Испеку пирог с яблоками 🍎', 18 * H),
      c(3, 301, 4, 'Могу взять краску для лавочек, какой цвет?', 6 * H),
      c(4, 301, 3, 'Зелёный, как в прошлом году', 5 * H),
    ],
    302: [
      c(5, 302, 2, 'Смету выложу в чат за день до собрания', 30 * H),
      c(6, 302, 1, 'Буду', 28 * H),
    ],
  }
}

export function buildAchievements(s: MockScenario): AchievementOut[] {
  const earned =
    s.name === 'empty'
      ? new Set<string>()
      : new Set(['first_issue', 'first_vote', 'helper', 'subbotnik'])
  const list: [string, string, string, string, number][] = [
    ['first_issue', 'Глаза дома', 'Сообщить о первой проблеме', 'mdi-eye-outline', 10],
    ['first_vote', 'Голос соседа', 'Поддержать чужую заявку', 'mdi-hand-back-right-outline', 5],
    ['helper', 'Добрая рука', 'Отдать вещь даром', 'mdi-gift-outline', 15],
    ['subbotnik', 'Чистый двор', 'Сходить на субботник', 'mdi-broom', 20],
    ['voter10', 'Активист', 'Поддержать 10 заявок', 'mdi-account-voice', 30],
    ['resolved', 'Дело сделано', 'Ваша заявка решена', 'mdi-check-decagram-outline', 25],
    ['organizer', 'Организатор', 'Создать событие', 'mdi-calendar-star', 20],
    ['seller', 'Купец', 'Разместить объявление', 'mdi-storefront-outline', 5],
    ['chatter', 'Душа компании', 'Написать 20 комментариев', 'mdi-chat-outline', 15],
    ['guardian', 'Хранитель', 'Набрать 500 очков', 'mdi-shield-star-outline', 50],
    ['safety', 'Готов ко всему', 'Посмотреть укрытия рядом', 'mdi-shield-home-outline', 5],
  ]
  return list.map(([code, title, description, icon, points], i) => ({
    code,
    title,
    description,
    icon,
    points,
    earned: earned.has(code),
    awarded_at: earned.has(code) ? at(-(i + 1) * 4 * D) : null,
  }))
}

export const SHELTERS: ShelterOut[] = [
  {
    id: 1,
    name: 'Укрытие в подвале школы (демо)',
    address: 'пр-т Ленинского Комсомола, 9',
    lat: 54.3868,
    lon: 48.609,
    capacity: 300,
    kind: 'basement',
    distance_m: 180,
    yandex_url: 'https://yandex.ru/maps/?rtext=~54.3868,48.609',
    osm_url: 'https://www.openstreetmap.org/?mlat=54.3868&mlon=48.609',
  },
  {
    id: 2,
    name: 'Цокольный этаж Дома культуры (демо)',
    address: 'пр-т Созидателей, 2',
    lat: 54.3846,
    lon: 48.6031,
    capacity: 600,
    kind: 'basement',
    distance_m: 420,
    yandex_url: 'https://yandex.ru/maps/?rtext=~54.3846,48.6031',
    osm_url: 'https://www.openstreetmap.org/?mlat=54.3846&mlon=48.6031',
  },
  {
    id: 3,
    name: 'Подземный паркинг ТЦ (демо)',
    address: 'пр-т Ленинского Комсомола, 30',
    lat: 54.3889,
    lon: 48.6118,
    capacity: 800,
    kind: 'parking',
    distance_m: 650,
    yandex_url: 'https://yandex.ru/maps/?rtext=~54.3889,48.6118',
    osm_url: 'https://www.openstreetmap.org/?mlat=54.3889&mlon=48.6118',
  },
]

export function buildAlert(s: MockScenario): AlertOut | null {
  if (s.name !== 'alert') return null
  return {
    id: 1,
    kind: 'drone',
    kind_title: 'Беспилотная опасность',
    message: 'Внимание! Угроза атаки беспилотников. Отойдите от окон, пройдите в укрытие.',
    active: true,
    created_at: at(-3 * 60_000),
    ended_at: null,
  }
}

export const MCP_SERVERS: McpServerOut[] = [
  {
    id: 1,
    name: 'housing_navigator',
    transport: 'streamable_http',
    url: 'http://mcp:8765/mcp',
    enabled: true,
    has_headers: false,
  },
]
