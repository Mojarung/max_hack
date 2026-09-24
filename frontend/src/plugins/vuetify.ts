import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
import { md3 } from 'vuetify/blueprints'
import { createVuetify } from 'vuetify'
import { ru } from 'vuetify/locale'

/**
 * Палитра проекта: только эти 9 цветов, других в интерфейсе нет.
 * 03045E 023E8A 0077B6 0096C7 00B4D8 48CAE4 90E0EF ADE8F4 CAF0F8
 * Статусы различаются не цветом, а иконкой и подписью (в палитре нет красного и зелёного).
 */
const P = {
  navy: '#03045E',
  indigo: '#023E8A',
  blue: '#0077B6',
  ocean: '#0096C7',
  cyan: '#00B4D8',
  sky: '#48CAE4',
  mist: '#90E0EF',
  frost: '#ADE8F4',
  ice: '#CAF0F8',
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
        variables: { 'medium-emphasis-opacity': 0.78 },
        colors: {
          primary: P.indigo,
          'on-primary': P.ice,
          'primary-container': P.frost,
          'on-primary-container': P.navy,
          secondary: P.blue,
          'on-secondary': P.ice,
          'secondary-container': P.mist,
          'on-secondary-container': P.navy,
          tertiary: P.ocean,
          'on-tertiary': P.ice,
          background: P.frost,
          'on-background': P.navy,
          surface: P.ice,
          'on-surface': P.navy,
          'surface-variant': P.mist,
          'on-surface-variant': P.indigo,
          'surface-bright': P.ice,
          'surface-light': P.frost,
          error: P.navy,
          'on-error': P.ice,
          warning: P.indigo,
          'on-warning': P.ice,
          success: P.blue,
          'on-success': P.ice,
          info: P.blue,
          'on-info': P.ice,
          muted: P.mist,
          'on-muted': P.indigo,
          light: P.ice,
          deep: P.navy,
          'on-deep': P.ice,
        },
      },
      dark: {
        dark: true,
        variables: { 'medium-emphasis-opacity': 0.78 },
        colors: {
          primary: P.sky,
          'on-primary': P.navy,
          'primary-container': P.blue,
          'on-primary-container': P.ice,
          secondary: P.mist,
          'on-secondary': P.navy,
          'secondary-container': P.blue,
          'on-secondary-container': P.ice,
          tertiary: P.cyan,
          'on-tertiary': P.navy,
          background: P.navy,
          'on-background': P.ice,
          surface: P.indigo,
          'on-surface': P.ice,
          'surface-variant': P.blue,
          'on-surface-variant': P.frost,
          'surface-bright': P.blue,
          'surface-light': P.indigo,
          error: P.frost,
          'on-error': P.navy,
          warning: P.mist,
          'on-warning': P.navy,
          success: P.sky,
          'on-success': P.navy,
          info: P.cyan,
          'on-info': P.navy,
          muted: P.ocean,
          'on-muted': P.ice,
          light: P.ice,
          // В тёмной теме фон уже navy: тревожное (просрочка, тревога) инвертируем в самый светлый
          deep: P.ice,
          'on-deep': P.navy,
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
