<script setup lang="ts">
import { gsap } from 'gsap'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import { prefersReducedMotion } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { openLink } from '@/max/bridge'
import { useAlertsStore } from '@/stores/alerts'
import { useSessionStore } from '@/stores/session'
import { formatDistance, formatTime } from '@/utils/format'

const alerts = useAlertsStore()
const session = useSessionStore()
const pulseLayer = ref<HTMLElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const ending = ref(false)
let pulseTween: gsap.core.Tween | null = null

const expanded = computed(() => !!alerts.active && !alerts.minimized)
const title = computed(() => alerts.active?.kind_title || 'Беспилотная опасность')

const INSTRUCTIONS = [
  { icon: 'mdi-window-closed-variant', text: 'Отойдите от окон и стеклянных дверей' },
  { icon: 'mdi-stairs-down', text: 'Спуститесь в укрытие или встаньте в коридоре без окон' },
  { icon: 'mdi-cellphone-off', text: 'Не снимайте и не выкладывайте видео с небом' },
  { icon: 'mdi-bell-ring-outline', text: 'Дождитесь сигнала «Отбой», Кузя сообщит' },
]

watch(
  expanded,
  async (open) => {
    pulseTween?.kill()
    pulseTween = null
    if (!open) return
    await nextTick()
    if (prefersReducedMotion()) return
    if (panel.value) {
      gsap.fromTo(
        panel.value,
        { opacity: 0, scale: 1.04 },
        { opacity: 1, scale: 1, duration: 0.35 },
      )
    }
    if (pulseLayer.value) {
      pulseTween = gsap.fromTo(
        pulseLayer.value,
        { opacity: 0.35 },
        { opacity: 1, duration: 0.9, repeat: -1, yoyo: true, ease: 'sine.inOut' },
      )
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => pulseTween?.kill())

function route(): void {
  if (alerts.nearest) openLink(alerts.nearest.yandex_url)
}

async function endAlert(): Promise<void> {
  ending.value = true
  try {
    await alerts.end()
  } catch (e) {
    notify.error(e, 'Не удалось дать отбой')
  } finally {
    ending.value = false
  }
}
</script>

<template>
  <!-- Свёрнутая тревога: полоса сверху, пока опасность не миновала -->
  <button
    v-if="alerts.active && alerts.minimized"
    type="button"
    class="alert-bar"
    aria-live="assertive"
    @click="alerts.minimized = false"
  >
    <v-icon icon="mdi-alert-octagon" size="22" />
    <span class="flex-1 text-left">Тревога: {{ title }}</span>
    <span class="alert-bar__open">Развернуть</span>
  </button>

  <div
    v-if="expanded && alerts.active"
    ref="panel"
    class="alert-overlay"
    role="alertdialog"
    aria-modal="true"
    aria-labelledby="alert-title"
    aria-describedby="alert-desc"
  >
    <div ref="pulseLayer" class="alert-overlay__pulse" aria-hidden="true" />
    <div class="alert-overlay__content">
      <div class="flex items-center gap-3">
        <KuzyaMascot mood="alarm" :size="84" :interactive="false" />
        <div>
          <div class="text-sm font-semibold opacity-90">
            Внимание! С {{ formatTime(alerts.active.created_at) }}
          </div>
          <h2 id="alert-title" class="m-0 text-[26px] leading-tight font-extrabold">{{ title }}</h2>
        </div>
      </div>

      <p v-if="alerts.active.message" id="alert-desc" class="mt-3 mb-0 text-[17px] font-medium">
        {{ alerts.active.message }}
      </p>
      <p v-else id="alert-desc" class="sr-only">Инструкция на случай беспилотной опасности</p>

      <ul class="mt-4 mb-0 flex list-none flex-col gap-2 p-0">
        <li v-for="item in INSTRUCTIONS" :key="item.text" class="alert-step">
          <v-icon :icon="item.icon" size="26" />
          <span>{{ item.text }}</span>
        </li>
      </ul>

      <div class="alert-shelter">
        <div class="text-sm font-semibold opacity-80">Ближайшее укрытие</div>
        <div v-if="alerts.nearestLoading" class="mt-1 flex items-center gap-2">
          <v-progress-circular indeterminate size="20" width="2" />
          Ищем укрытие рядом с вами...
        </div>
        <template v-else-if="alerts.nearest">
          <div class="mt-1 text-lg leading-snug font-bold">{{ alerts.nearest.name }}</div>
          <div class="text-sm opacity-90">
            {{ alerts.nearest.address }}
            <template v-if="alerts.nearest.distance_m !== null">
              · {{ formatDistance(alerts.nearest.distance_m) }}
            </template>
          </div>
        </template>
        <div v-else class="mt-1">
          Не удалось найти укрытие. Спуститесь в подвал или коридор без окон.
          <v-btn variant="text" color="light" size="small" @click="alerts.findNearest()">
            Повторить
          </v-btn>
        </div>
      </div>

      <v-btn
        block
        size="x-large"
        color="light"
        class="alert-route mt-4"
        prepend-icon="mdi-walk"
        :disabled="!alerts.nearest"
        @click="route"
      >
        Маршрут до укрытия
      </v-btn>
      <div class="mt-2 flex gap-2">
        <v-btn
          class="flex-1"
          variant="outlined"
          color="light"
          size="large"
          prepend-icon="mdi-arrow-collapse-up"
          @click="alerts.minimized = true"
        >
          Свернуть
        </v-btn>
        <v-btn
          v-if="session.canUseDevTools || session.isAdmin"
          class="flex-1"
          variant="outlined"
          color="light"
          size="large"
          prepend-icon="mdi-check"
          :loading="ending"
          @click="endAlert"
        >
          Отбой
        </v-btn>
      </div>
    </div>
  </div>
</template>

<style scoped>
.alert-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  overflow-y: auto;
  color: #caf0f8;
  background: #03045e;
}
.alert-overlay__pulse {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 50% 20%, #0096c7 0%, #023e8a 45%, #03045e 100%);
  pointer-events: none;
}
.alert-overlay__content {
  position: relative;
  max-width: var(--app-max-width);
  margin: 0 auto;
  padding: calc(20px + env(safe-area-inset-top)) 16px calc(24px + env(safe-area-inset-bottom));
}
.alert-step {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(3, 4, 94, 0.35);
  font-size: 17px;
  font-weight: 600;
  line-height: 1.3;
}
.alert-shelter {
  margin-top: 16px;
  padding: 14px;
  border-radius: 16px;
  background: rgba(202, 240, 248, 0.14);
  border: 1px solid rgba(202, 240, 248, 0.3);
}
.alert-route {
  color: #023e8a !important;
  font-weight: 800;
}
.alert-bar {
  position: fixed;
  top: env(safe-area-inset-top);
  left: 0;
  right: 0;
  z-index: 1500;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 52px;
  padding: 8px 16px;
  border: 0;
  color: #caf0f8;
  font-size: 16px;
  font-weight: 700;
  background: #023e8a;
  animation: alert-bar-blink 1.6s ease-in-out infinite;
  cursor: pointer;
}
.alert-bar__open {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(202, 240, 248, 0.2);
  font-size: 14px;
}
@keyframes alert-bar-blink {
  50% {
    background: #0077b6;
  }
}
</style>
