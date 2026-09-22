import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
import { md3 } from 'vuetify/blueprints'
import { createVuetify } from 'vuetify'
import { ru } from 'vuetify/locale'

/** Тёплая палитра «очага»: оранжево-янтарный primary, бирюзовый secondary. */
export const vuetify = createVuetify({
  blueprint: md3,
  locale: { locale: 'ru', messages: { ru } },
  theme: {
    defaultTheme: 'system',
    themes: {
      light: {
        dark: false,
        colors: {
          primary: '#B8501A',
          'on-primary': '#FFFFFF',
          'primary-container': '#FFDBC8',
          'on-primary-container': '#3A1300',
          secondary: '#00796B',
          'on-secondary': '#FFFFFF',
          'secondary-container': '#C8EDE6',
          background: '#FFF8F3',
          surface: '#FFFFFF',
          'surface-variant': '#F6E8DF',
          'on-surface-variant': '#52443C',
          error: '#C62828',
          warning: '#B26A00',
          success: '#2E7D32',
          info: '#0B6BA8',
        },
      },
      dark: {
        dark: true,
        colors: {
          primary: '#FFB68C',
          'on-primary': '#552000',
          'primary-container': '#7A3300',
          'on-primary-container': '#FFDBC8',
          secondary: '#6FD6C6',
          'on-secondary': '#00382F',
          'secondary-container': '#005047',
          background: '#1A120E',
          surface: '#241B16',
          'surface-variant': '#3A2E27',
          'on-surface-variant': '#D7C2B8',
          error: '#FF8A80',
          warning: '#FFB74D',
          success: '#81C784',
          info: '#81D4FA',
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
