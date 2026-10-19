/**
 * Готовые аватарки: девять войлочных шариков в public/avatars (режет scripts/avatars.py).
 * Житель без фото получает картинку по своему id, в профиле может выбрать любую или загрузить своё фото.
 */
export const PRESET_COUNT = 9

export function presetAvatar(n: number): string {
  return `${import.meta.env.BASE_URL}avatars/${n}.webp`
}

/** Номер картинки по id: у одного жителя всегда одна и та же. */
export function defaultPreset(userId: number): number {
  return (Math.abs(userId) % PRESET_COUNT) + 1
}

/** Номер выбранной картинки из поля avatar («preset:N»), иначе null. */
export function chosenPreset(avatar: string | null | undefined): number | null {
  const m = /^preset:(\d)$/.exec(avatar ?? '')
  const n = m ? Number(m[1]) : 0
  return n >= 1 && n <= PRESET_COUNT ? n : null
}
