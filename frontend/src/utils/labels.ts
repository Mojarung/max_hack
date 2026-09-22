import type { EventKind, IssueStatus, ListingStatus, Mood } from '@/api/types'

export const ISSUE_STATUSES: { value: IssueStatus | null; title: string }[] = [
  { value: null, title: 'Все' },
  { value: 'voting', title: 'Голосование' },
  { value: 'sent', title: 'Отправлено' },
  { value: 'in_progress', title: 'В работе' },
  { value: 'resolved', title: 'Решено' },
  { value: 'rejected', title: 'Отклонено' },
]

export const ISSUE_STATUS_META: Record<IssueStatus, { color: string; icon: string }> = {
  voting: { color: 'warning', icon: 'mdi-account-multiple-plus' },
  sent: { color: 'info', icon: 'mdi-email-fast-outline' },
  in_progress: { color: 'secondary', icon: 'mdi-hammer-wrench' },
  resolved: { color: 'success', icon: 'mdi-check-circle' },
  rejected: { color: 'grey', icon: 'mdi-close-circle-outline' },
}

export const ISSUE_CATEGORY_ICONS: Record<string, string> = {
  roof: 'mdi-home-roof',
  water: 'mdi-water-pump',
  plumbing: 'mdi-pipe-leak',
  heating: 'mdi-radiator',
  electricity: 'mdi-flash',
  elevator: 'mdi-elevator-passenger',
  lighting: 'mdi-lightbulb-outline',
  garbage: 'mdi-delete-outline',
  cleaning: 'mdi-broom',
  yard: 'mdi-tree-outline',
  road: 'mdi-road-variant',
  noise: 'mdi-volume-high',
  entrance: 'mdi-door',
  intercom: 'mdi-doorbell',
  gas: 'mdi-fire',
  other: 'mdi-alert-circle-outline',
}

export function issueCategoryIcon(category: string): string {
  return ISSUE_CATEGORY_ICONS[category] ?? 'mdi-alert-circle-outline'
}

export const LISTING_CATEGORY_TITLES: Record<string, string> = {
  furniture: 'Мебель',
  electronics: 'Техника',
  kids: 'Детское',
  clothes: 'Одежда',
  tools: 'Инструменты',
  plants: 'Растения',
  food: 'Еда',
  services: 'Услуги',
  other: 'Разное',
}

export const LISTING_CATEGORY_ICONS: Record<string, string> = {
  furniture: 'mdi-sofa-outline',
  electronics: 'mdi-television',
  kids: 'mdi-baby-carriage',
  clothes: 'mdi-tshirt-crew-outline',
  tools: 'mdi-hammer-screwdriver',
  plants: 'mdi-sprout-outline',
  food: 'mdi-food-apple-outline',
  services: 'mdi-hand-heart-outline',
  other: 'mdi-shape-outline',
}

export const LISTING_STATUS_META: Record<ListingStatus, { title: string; color: string }> = {
  active: { title: 'Активно', color: 'success' },
  reserved: { title: 'Забронировано', color: 'warning' },
  closed: { title: 'Закрыто', color: 'grey' },
}

export const EVENT_KINDS: { value: EventKind; title: string; icon: string; color: string }[] = [
  { value: 'subbotnik', title: 'Субботник', icon: 'mdi-broom', color: 'success' },
  { value: 'meeting', title: 'Собрание', icon: 'mdi-account-group', color: 'info' },
  { value: 'holiday', title: 'Праздник', icon: 'mdi-party-popper', color: 'primary' },
  { value: 'sport', title: 'Спорт', icon: 'mdi-soccer', color: 'secondary' },
  { value: 'kids', title: 'Для детей', icon: 'mdi-teddy-bear', color: 'pink' },
  { value: 'other', title: 'Другое', icon: 'mdi-calendar-star', color: 'grey-darken-1' },
]

export function eventKindMeta(kind: string): { title: string; icon: string; color: string } {
  return EVENT_KINDS.find((k) => k.value === kind) ?? EVENT_KINDS[EVENT_KINDS.length - 1]!
}

export const MOOD_TITLES: Record<Mood, string> = {
  happy: 'Кузя доволен',
  ok: 'Кузя спокоен',
  worried: 'Кузя волнуется',
  sad: 'Кузя грустит',
  alarm: 'Кузя бьёт тревогу',
}

/** Цвет «здоровья дома» по шкале 0..100. */
export function scoreColor(score: number): string {
  if (score >= 75) return 'success'
  if (score >= 50) return 'warning'
  return 'error'
}

export const ASSISTANT_TOOL_TITLES: Record<string, string> = {
  search_issues: 'проблемы дома',
  get_issue: 'карточку проблемы',
  search_events: 'события',
  create_event: 'создание события',
  search_listings: 'барахолку',
  find_shelters: 'укрытия',
  get_shelters: 'укрытия',
  house_pulse: 'состояние дома',
  get_pulse: 'состояние дома',
}
