import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
import { md3 } from 'vuetify/blueprints'
import { createVuetify } from 'vuetify'
import { ru } from 'vuetify/locale'

/**
 * Палитра: спокойная нейтральная основа, синий - фирменный и главное действие,
 * смысловые цвета только для состояний (DESIGN.md → «Палитра»). Цвет всегда дублирует
 * иконку и подпись, а не заменяет их. Все пары текст/фон проверены на WCAG AA.
 */
const L = {
  bg: '#F5F7FA',
  surface: '#FFFFFF',
  ink: '#1B2533',
  inkSoft: '#4A5668',
  line: '#D5DCE5',
  blue: '#1F5FAF',
  blueSoft: '#E4EDF8',
  teal: '#0F766E',
  tealSoft: '#DDF1EE',
  violet: '#7B4FA0',
  green: '#1E7B45',
  amber: '#8A5300',
  red: '#C62828',
  muted: '#E8ECF1',
} as const

const D = {
  bg: '#11151B',
  surface: '#1B212A',
  surfaceHigh: '#252D38',
  ink: '#E7ECF2',
  inkSoft: '#A9B4C2',
  blue: '#7FB3F5',
  blueDeep: '#0B1B33',
  blueSoft: '#22344D',
  teal: '#5EC7BC',
  violet: '#C3A6EB',
  green: '#5BC98A',
  amber: '#F4C15D',
  redText: '#FF8A80',
  red: '#B3261E',
  muted: '#2A3240',
} as const

export const vuetify = createVuetify({
  blueprint: md3,
  locale: { locale: 'ru', messages: { ru } },
  theme: {
    defaultTheme: 'system',
    themes: {
      light: {
        dark: false,
        // подписи полей и второстепенный текст Vuetify: контраст не ниже WCAG AA
        variables: { 'medium-emphasis-opacity': 0.78, 'border-color': '#1B2533' },
        colors: {
          primary: L.blue,
          'on-primary': '#FFFFFF',
          'primary-container': L.blueSoft,
          'on-primary-container': '#123A6B',
          secondary: L.teal,
          'on-secondary': '#FFFFFF',
          'secondary-container': L.tealSoft,
          'on-secondary-container': '#0B4A45',
          tertiary: L.violet,
          'on-tertiary': '#FFFFFF',
          background: L.bg,
          'on-background': L.ink,
          surface: L.surface,
          'on-surface': L.ink,
          'surface-variant': L.muted,
          'on-surface-variant': L.inkSoft,
          'surface-bright': L.surface,
          'surface-light': L.muted,
          error: L.red,
          'on-error': '#FFFFFF',
          warning: L.amber,
          'on-warning': '#FFFFFF',
          success: L.green,
          'on-success': '#FFFFFF',
          info: L.blue,
          'on-info': '#FFFFFF',
          muted: L.muted,
          'on-muted': L.inkSoft,
          light: L.surface,
          // тревога и просрочка: красная заливка с белым текстом
          deep: L.red,
          'on-deep': '#FFFFFF',
          // сильный нейтральный: служебные кнопки поверх фото, счётчики
          ink: L.ink,
          'on-ink': '#FFFFFF',
        },
      },
      dark: {
        dark: true,
        variables: { 'medium-emphasis-opacity': 0.78, 'border-color': '#E7ECF2' },
        colors: {
          primary: D.blue,
          'on-primary': D.blueDeep,
          'primary-container': D.blueSoft,
          'on-primary-container': '#D6E6FB',
          secondary: D.teal,
          'on-secondary': '#0B1F1D',
          'secondary-container': '#17403C',
          'on-secondary-container': '#C8F0EB',
          tertiary: D.violet,
          'on-tertiary': '#1E1030',
          background: D.bg,
          'on-background': D.ink,
          surface: D.surface,
          'on-surface': D.ink,
          'surface-variant': D.muted,
          'on-surface-variant': D.inkSoft,
          'surface-bright': D.surfaceHigh,
          'surface-light': D.surfaceHigh,
          error: D.redText,
          'on-error': '#2A0B08',
          warning: D.amber,
          'on-warning': '#1B2533',
          success: D.green,
          'on-success': '#0B2415',
          info: D.blue,
          'on-info': D.blueDeep,
          muted: D.muted,
          'on-muted': '#C9D1DC',
          light: D.ink,
          // тревога в тёмной теме тоже красная заливка, а не «самый светлый» цвет
          deep: D.red,
          'on-deep': '#FFFFFF',
          ink: D.ink,
          'on-ink': D.bg,
        },
      },
    },
  },
  defaults: {
    VBtn: { rounded: 'lg' },
    VCard: { rounded: 'xl' },
    VTextField: { variant: 'outlined', rounded: 'lg', color: 'primary', hideDetails: 'auto' },
    VTextarea: { variant: 'outlined', rounded: 'lg', color: 'primary', hideDetails: 'auto' },
    VSelect: { variant: 'outlined', rounded: 'lg', color: 'primary', hideDetails: 'auto' },
    VChip: { rounded: 'lg' },
    VProgressLinear: { rounded: true },
  },
})
