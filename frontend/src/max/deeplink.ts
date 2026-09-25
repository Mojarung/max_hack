/**
 * Разбор параметра запуска (`start_param`) и payload кнопок `open_app`.
 * Разрешены только известные форматы: `issue_5`, `event_3`, `listing_2`,
 * `alert`, `safety`, `issues`, `events`, `market`, `home`.
 */
/** Ссылка, которая откроет заявку в мини-приложении MAX (null, если ник бота неизвестен). */
export function issueDeepLink(id: number, botUsername: string | null | undefined): string | null {
  return botUsername ? `https://max.ru/${botUsername}?startapp=issue_${id}` : null
}

export function deepLinkToPath(raw: string | null | undefined): string | null {
  if (!raw) return null
  const value = raw.trim().toLowerCase()
  const match = /^(issue|event|listing)_(\d{1,9})$/.exec(value)
  if (match) {
    const [, kind, id] = match
    if (kind === 'issue') return `/issues/${id}`
    if (kind === 'event') return `/events/${id}`
    return `/market/${id}`
  }
  const simple: Record<string, string> = {
    alert: '/more/safety',
    safety: '/more/safety',
    shelters: '/more/safety',
    issues: '/issues',
    new_issue: '/issues/new',
    events: '/events',
    market: '/market',
    listings: '/market',
    achievements: '/more/achievements',
    announcements: '/announcements',
    documents: '/more/documents',
    house: '/more/house',
    house_setup: '/more/house/edit',
    people: '/people',
    home: '/',
  }
  return simple[value] ?? null
}
