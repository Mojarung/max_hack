<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppHeader from '@/components/layout/AppHeader.vue'
import BootScreen from '@/components/layout/BootScreen.vue'
import BottomNav from '@/components/layout/BottomNav.vue'
import { Toaster } from '@/components/ui/sonner'
import { pageEnter, pageLeave } from '@/composables/useMotion'
import { installAutoReveal } from '@/composables/useReveal'
import { backButton, getStartParam } from '@/max/bridge'
import { deepLinkToPath } from '@/max/deeplink'
import { goBack } from '@/router'
import { useAlertsStore } from '@/stores/alerts'
import { usePulseStore } from '@/stores/pulse'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const alerts = useAlertsStore()
const pulse = usePulseStore()
const route = useRoute()
const alertOpen = computed(() => !!alerts.active && !alerts.minimized)
const router = useRouter()
let deepLinkHandled = false

// Оверлей тревоги загружается только во время тревоги
const DroneAlertOverlay = defineAsyncComponent(
  () => import('@/components/safety/DroneAlertOverlay.vue'),
)

// Анимация появления блоков при прокрутке на всех экранах
const mainEl = ref<HTMLElement | null>(null)
let stopReveal: (() => void) | null = null
watch(mainEl, (el) => {
  stopReveal?.()
  stopReveal = el ? installAutoReveal(el) : null
})
onBeforeUnmount(() => stopReveal?.())

onMounted(() => void session.init())

watch(
  () => session.status,
  async (status) => {
    if (status !== 'ready') return
    void alerts.check()
    void pulse.load()
    if (deepLinkHandled) return
    deepLinkHandled = true
    await router.isReady()
    const target = deepLinkToPath(getStartParam())
    if (target && route.path === '/') await router.push(target)
  },
)

// Системная кнопка «Назад» в MAX на внутренних страницах
watch(
  () => route.meta.inner,
  (inner) => (inner ? backButton.show(goBack) : backButton.hide()),
  { immediate: true },
)
</script>

<template>
  <v-app>
    <BootScreen v-if="session.status !== 'ready'" />
    <template v-else>
      <!-- Пока открыт экран тревоги, всё под ним недоступно для фокуса и диктора -->
      <AppHeader :inert="alertOpen" />
      <main ref="mainEl" :inert="alertOpen">
        <router-view v-slot="{ Component, route: current }">
          <Transition :css="false" mode="out-in" @enter="pageEnter" @leave="pageLeave">
            <component :is="Component" :key="`${current.path}#${session.userKey}`" />
          </Transition>
        </router-view>
      </main>
      <BottomNav :inert="alertOpen" />
    </template>
    <DroneAlertOverlay v-if="alerts.active" />
    <Toaster />
  </v-app>
</template>
