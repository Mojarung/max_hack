import { describe, expect, it } from 'vitest'
import { vuetify } from './vuetify'

const themes = vuetify.theme.themes.value

describe('тема приложения', () => {
  it('две темы, по умолчанию как в системе', () => {
    expect(themes.light?.dark).toBe(false)
    expect(themes.dark?.dark).toBe(true)
    expect(vuetify.theme.name.value).toBe('light')
  })

  it('синий - главное действие, тревога - красная заливка с белым текстом в обеих темах', () => {
    expect(themes.light?.colors.primary).toBe('#1F5FAF')
    for (const theme of [themes.light, themes.dark]) {
      expect(theme?.colors['on-deep']).toBe('#FFFFFF')
    }
    expect(themes.light?.colors.deep).toBe('#C62828')
    expect(themes.dark?.colors.deep).toBe('#B3261E')
  })

  it('подписи по-русски', () => {
    expect(vuetify.locale.current.value).toBe('ru')
    expect(vuetify.locale.t('$vuetify.close')).toBe('Закрыть')
  })
})
