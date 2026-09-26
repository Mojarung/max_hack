/**
 * Настроения маскота «Домовой Кузя». Каждое настроение - отдельная нарисованная поза
 * с листа art/kuzya-sheet.png, слои режет scripts/kuzya_sprites.py.
 */

export type KuzyaMood = 'happy' | 'ok' | 'worried' | 'sad' | 'alarm' | 'proud'

export const MOOD_LABELS: Record<KuzyaMood, string> = {
  happy: 'Домовой Кузя радуется',
  ok: 'Домовой Кузя спокоен',
  worried: 'Домовой Кузя удивлён',
  sad: 'Домовой Кузя грустит',
  alarm: 'Домовой Кузя бьёт тревогу',
  proud: 'Домовой Кузя гордится',
}

/**
 * Поза, которую Кузя на секунду принимает в ответ на нажатие. Пока в доме просрочка
 * или тревога, он не радуется, а только подпрыгивает (null).
 */
export function tapPose(mood: KuzyaMood): KuzyaMood | null {
  if (mood === 'sad' || mood === 'alarm') return null
  return mood === 'happy' ? 'proud' : 'happy'
}
