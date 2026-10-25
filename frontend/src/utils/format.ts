import type { UserShort } from '@/api/types'

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** Русское склонение: plural(3, ['голос', 'голоса', 'голосов']) -> 'голоса'. */
export function plural(n: number, forms: [string, string, string]): string {
  const abs = Math.abs(Math.trunc(n))
  const mod10 = abs % 10
  const mod100 = abs % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1]
  return forms[2]
}

export function pluralize(n: number, forms: [string, string, string]): string {
  return `${n} ${plural(n, forms)}`
}

export interface Countdown {
  overdue: boolean
  text: string
  /** Меньше 3 часов до срока. */
  urgent: boolean
}

/**
 * Формат таймера срока: «2 д 5 ч», «3 ч 15 мин», «12 мин», «меньше минуты».
 * Отрицательный остаток означает просрочку: «просрочено на 5 ч».
 */
export function formatCountdown(msLeft: number): Countdown {
  const overdue = msLeft < 0
  const ms = Math.abs(msLeft)
  let text: string
  if (ms < MINUTE) {
    text = 'меньше минуты'
  } else if (ms < HOUR) {
    text = `${Math.floor(ms / MINUTE)} мин`
  } else if (ms < DAY) {
    const h = Math.floor(ms / HOUR)
    const m = Math.floor((ms % HOUR) / MINUTE)
    text = m > 0 ? `${h} ч ${m} мин` : `${h} ч`
  } else {
    const d = Math.floor(ms / DAY)
    const h = Math.floor((ms % DAY) / HOUR)
    text = h > 0 ? `${d} д ${h} ч` : `${d} д`
  }
  return {
    overdue,
    urgent: !overdue && ms < 3 * HOUR,
    text: overdue ? `просрочено на ${text}` : text,
  }
}

function toDate(value: string | Date): Date {
  return value instanceof Date ? value : new Date(value)
}

const dateTimeFmt = new Intl.DateTimeFormat('ru-RU', {
  weekday: 'short',
  day: 'numeric',
  month: 'long',
  hour: '2-digit',
  minute: '2-digit',
})
const dateFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' })
const timeFmt = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' })

export function formatDateTime(value: string | Date): string {
  return dateTimeFmt.format(toDate(value))
}

export function formatDate(value: string | Date): string {
  return dateFmt.format(toDate(value))
}

export function formatTime(value: string | Date): string {
  return timeFmt.format(toDate(value))
}

/** «только что», «5 мин назад», «3 ч назад», «вчера», иначе дата. */
export function formatRelative(value: string | Date, now: number = Date.now()): string {
  const diff = now - toDate(value).getTime()
  if (diff < MINUTE) return 'только что'
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)} мин назад`
  if (diff < DAY) return `${Math.floor(diff / HOUR)} ч назад`
  if (diff < 2 * DAY) return 'вчера'
  return formatDate(value)
}

/** Нормативный срок для жителя: «24 часа», от 48 часов - днями: «7 дней». */
export function formatHours(hours: number): string {
  const days = Math.round(hours / 24)
  if (hours >= 48) return `${days}\u00a0${plural(days, ['день', 'дня', 'дней'])}`
  return `${hours}\u00a0${plural(hours, ['час', 'часа', 'часов'])}`
}

export function formatDistance(meters: number | null | undefined): string {
  if (meters === null || meters === undefined || Number.isNaN(meters)) return ''
  if (meters < 1000) return `${Math.round(meters / 10) * 10} м`
  return `${(meters / 1000).toFixed(1).replace('.', ',')} км`
}

/**
 * Строка маршрута пешком: «≈ 7 мин пешком · 540 м», от часа - «≈ 1 ч 10 мин пешком · 5,2 км».
 * Меньше минуты округляем до одной: «меньше минуты» в тревоге читается хуже цифры.
 */
export function formatWalk(distanceM: number, durationS: number): string {
  const minutes = Math.max(1, Math.round(durationS / 60))
  const time =
    minutes < 60
      ? `${minutes} мин`
      : `${Math.floor(minutes / 60)} ч${minutes % 60 ? ` ${minutes % 60} мин` : ''}`
  return `≈ ${time} пешком · ${formatDistance(distanceM)}`
}

const priceFmt = new Intl.NumberFormat('ru-RU')

export function formatPrice(price: number, isFree: boolean): string {
  if (isFree || price <= 0) return 'Даром'
  return `${priceFmt.format(price)} ₽`
}

export function fullName(
  user: Pick<UserShort, 'first_name' | 'last_name'> | null | undefined,
): string {
  if (!user) return 'Житель'
  return [user.first_name, user.last_name].filter(Boolean).join(' ') || 'Житель'
}

export function initials(
  user: Pick<UserShort, 'first_name' | 'last_name'> | null | undefined,
): string {
  if (!user) return '?'
  const a = user.first_name?.[0] ?? ''
  const b = user.last_name?.[0] ?? ''
  return (a + b).toUpperCase() || '?'
}

/** Дистанция между точками по формуле гаверсинусов, в метрах. */
export function haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6_371_000
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

/**
 * Название организации словами жителя: без «УК», «ТКО» и «ГЖИ».
 * «УК «Уютный дом»» → «управляющая компания «Уютный дом»»,
 * «Регоператор ТКО «Гринта»» → «оператор вывоза мусора «Гринта»».
 */
export function orgTitle(name: string | null | undefined): string {
  if (!name) return ''
  return plainOrgWords(name).trim()
}

const NOT_LETTER = '(^|[^А-Яа-яЁё])'

/** Раскрывает сокращения в любом месте текста: «УК: бригада на месте» → «управляющая компания: …». */
export function plainOrgWords(text: string): string {
  return text
    .replace(new RegExp(`${NOT_LETTER}УК(?![А-Яа-яЁё])`, 'g'), '$1управляющая компания')
    .replace(/Рег(иональный)?\s*оператор(\s+по\s+обращению\s+с)?\s+ТКО/gi, 'оператор вывоза мусора')
    .replace(new RegExp(`${NOT_LETTER}ГЖИ(?![А-Яа-яЁё])`, 'g'), '$1Госжилинспекция')
}

/** Первая буква заглавная. */
export function capitalize(text: string): string {
  return text ? text[0]!.toUpperCase() + text.slice(1) : text
}

/** Винительный падеж: «обязать управляющую компанию «Уютный дом»». */
export function orgAccusative(name: string | null | undefined): string {
  return orgTitle(name)
    .replace(/^управляющая компания/, 'управляющую компанию')
    .replace(/^оператор вывоза мусора/, 'оператора вывоза мусора')
    .replace(/^Госжилинспекция/, 'Госжилинспекцию')
}

/** Куда уходит обращение: «Кузя отправит его в управляющую компанию …» / «… оператору вывоза мусора …». */
export function orgRecipient(name: string | null | undefined): string {
  const t = orgTitle(name)
  if (!t) return ''
  if (t.startsWith('оператор вывоза мусора')) return t.replace(/^оператор/, 'оператору')
  if (/^(управляющая компания|Госжилинспекция)/.test(t)) return `в ${orgAccusative(name)}`
  // название без вида организации: не угадываем падеж
  return `в организацию ${t}`
}

/** То же с заглавной буквы: для начала строки и заголовков. */
export function orgTitleCap(name: string | null | undefined): string {
  const t = orgTitle(name)
  return t ? t[0]!.toUpperCase() + t.slice(1) : t
}

/**
 * Жирный текст из markdown бота (`**…**`) без v-html: MAX рендерит его сам,
 * эмулятору чата нужны куски «обычный / жирный». Непарные звёздочки остаются как есть.
 */
export function boldSegments(text: string): { text: string; bold: boolean }[] {
  const parts: { text: string; bold: boolean }[] = []
  let last = 0
  for (const m of text.matchAll(/\*\*(.+?)\*\*/gs)) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index), bold: false })
    parts.push({ text: m[1]!, bold: true })
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last), bold: false })
  return parts
}
