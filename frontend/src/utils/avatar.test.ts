import { describe, expect, it } from 'vitest'
import { chosenPreset, defaultPreset, presetAvatar, PRESET_COUNT } from './avatar'

describe('готовые аватарки', () => {
  it('ссылка на картинку из public/avatars', () => {
    expect(presetAvatar(3)).toBe('/avatars/3.webp')
  })

  it('у одного жителя всегда одна и та же картинка из девяти', () => {
    expect(defaultPreset(1)).toBe(2)
    expect(defaultPreset(1)).toBe(defaultPreset(1))
    expect(defaultPreset(9)).toBe(1)
    expect(defaultPreset(-4)).toBe(5)
    for (const id of [0, 7, 100, 12345]) {
      expect(defaultPreset(id)).toBeGreaterThanOrEqual(1)
      expect(defaultPreset(id)).toBeLessThanOrEqual(PRESET_COUNT)
    }
  })

  it('понимает выбор «preset:N» и игнорирует остальное', () => {
    expect(chosenPreset('preset:4')).toBe(4)
    expect(chosenPreset('preset:0')).toBeNull()
    expect(chosenPreset('preset:12')).toBeNull()
    expect(chosenPreset('upload')).toBeNull()
    expect(chosenPreset(null)).toBeNull()
    expect(chosenPreset(undefined)).toBeNull()
  })
})
