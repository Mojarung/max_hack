import './styles/main.css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import { installDragScroll } from './composables/useDragScroll'
import { MOCK_API } from './api/mode'
import { vuetify } from './plugins/vuetify'
import { router } from './router'

if (MOCK_API) {
  const [{ installMockBridge }, { scenario }] = await Promise.all([
    import('./mock/bridge'),
    import('./mock/scenario'),
  ])
  installMockBridge()
  if (scenario.theme) void vuetify.theme.change(scenario.theme)
  // аудит интерфейса нужен только разработке, демо в браузере его не грузит
  if (import.meta.env.VITE_MOCK_API === 'true') (await import('./mock/audit')).installAudit()
}

installDragScroll()
createApp(App).use(createPinia()).use(router).use(vuetify).mount('#app')
