// Сгенерировано scripts/kuzya_sprites.py из art/kuzya-sheet.png, руками не править.
import type { KuzyaMood } from './mood'

export const CANVAS = { width: 472, height: 500, ground: 494 } as const

export interface PoseMeta {
  /** Точка шеи на холсте: вокруг неё качается голова. */
  neck: [number, number]
  /** Есть слой закрытых век. */
  blink: boolean
}

export const POSES: Record<KuzyaMood, PoseMeta> = {
  ok: { neck: [236, 262], blink: true },
  happy: { neck: [236, 246], blink: false },
  proud: { neck: [236, 264], blink: false },
  sad: { neck: [236, 291], blink: true },
  alarm: { neck: [236, 280], blink: false },
  worried: { neck: [236, 252], blink: true },
}
