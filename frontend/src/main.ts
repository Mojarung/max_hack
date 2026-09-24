import './styles/main.css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import { vuetify } from './plugins/vuetify'
import { router } from './router'

if (import.meta.env.VITE_MOCK_API === 'true') {
  const [{ installMockBridge }, { installAudit }] = await Promise.all([
    import('./mock/bridge'),
    import('./mock/audit'),
  ])
  installMockBridge()
  installAudit()
  const { scenario } = await import('./mock/scenario')
  if (scenario.theme) void vuetify.theme.change(scenario.theme)
}

createApp(App).use(createPinia()).use(router).use(vuetify).mount('#app')
