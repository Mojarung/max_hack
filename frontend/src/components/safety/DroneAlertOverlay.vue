<script setup lang="ts">
import { gsap } from 'gsap'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import { ALERT_INSTRUCTIONS as INSTRUCTIONS } from '@/components/safety/instructions'
import { prefersReducedMotion } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { openLink } from '@/max/bridge'
import { useAlertsStore } from '@/stores/alerts'
import { useSessionStore } from '@/stores/session'
import { formatDistance, formatTime } from '@/utils/format'

const alerts = useAlertsStore()
const session = useSessionStore()
const router = useRouter()
const pulseLayer = ref<HTMLElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const ending = ref(false)
let pulseTween: gsap.core.Tween | null = null

const expanded = computed(() => !!alerts.active && !alerts.minimized)
const title = computed(() => alerts.active?.kind_title || 'Беспилотная опасность')

watch(
  expanded,
  async (open) => {
    pulseTween?.kill()
    pulseTween = null
    if (!open) return
    await nextTick()
    // Фокус в диалог: диктор читает заголовок, дальше по Tab - маршрут (кнопка может быть
    // ещё неактивна, пока ищем укрытие, поэтому фокусируем сам диалог)
    panel.value?.focus()
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
        { opacity: 0.4 },
        { opacity: 1, duration: 1.6, repeat: -1, yoyo: true, ease: 'sine.inOut' },
      )
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => pulseTween?.kill())

/** Маршрут на карте приложения: сворачиваем тревогу в полосу и открываем укрытие на экране «Безопасность». */
function showRoute(): void {
  if (!alerts.nearest) return
  alerts.minimized = true
  void router.push({ path: '/more/safety', query: { shelter: String(alerts.nearest.id) } })
}

function openYandex(): void {
  if (!alerts.nearest) return
  // карта открывается не мгновенно: без подсказки житель нажмёт ещё раз
  notify.info('Открываю Яндекс Карты с маршрутом...')
  openLink(alerts.nearest.yandex_url)
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
    tabindex="-1"
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
            {{ alerts.nearest.kind_title
            }}<template v-if="alerts.nearest.address"> · {{ alerts.nearest.address }}</template>
            <template v-if="alerts.nearest.distance_m !== null">
              · {{ formatDistance(alerts.nearest.distance_m) }}
            </template>
          </div>
          <div class="mt-1 text-sm opacity-80">
            {{
              alerts.nearest.official
                ? 'Из реестра укрытий'
                : `По данным: ${alerts.nearest.source_title}`
            }}
          </div>
        </template>
        <div v-else class="mt-1">
          Рядом не нашлось укрытий в реестре и на карте. Спуститесь в подвал или встаньте в
          помещении без окон.
          <v-btn variant="text" color="light" size="small" @click="alerts.findNearest()">
            Повторить
          </v-btn>
        </div>
      </div>

      <!-- Две кнопки маршрута друг под другом: в ряд «В Яндекс Картах» не влезает на 375px -->
      <v-btn
        block
        size="x-large"
        color="light"
        class="alert-route mt-4"
        prepend-icon="mdi-map-marker-path"
        :disabled="!alerts.nearest"
        @click="showRoute"
      >
        Маршрут
      </v-btn>
      <v-btn
        block
        size="large"
        variant="outlined"
        color="light"
        class="mt-2"
        prepend-icon="mdi-open-in-new"
        aria-label="Маршрут до укрытия в Яндекс Картах"
        :disabled="!alerts.nearest"
        @click="openYandex"
      >
        В Яндекс Картах
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
  outline: none;
  position: fixed;
  inset: 0;
  z-index: 3000;
  overflow-y: auto;
  color: rgb(var(--v-theme-on-deep));
  background: rgb(var(--v-theme-deep));
}
.alert-overlay__pulse {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 50% 15%, rgba(255, 255, 255, 0.18) 0%, transparent 60%);
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
  border-radius: var(--r-md);
  background: rgba(0, 0, 0, 0.18);
  font-size: 17px;
  font-weight: 600;
  line-height: 1.3;
}
.alert-shelter {
  margin-top: 16px;
  padding: 14px;
  border-radius: var(--r-md);
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.3);
}
.alert-route {
  color: rgb(var(--v-theme-deep)) !important;
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
  color: rgb(var(--v-theme-on-deep));
  font-size: 16px;
  font-weight: 700;
  background: rgb(var(--v-theme-deep));
  animation: alert-bar-blink 1.6s ease-in-out infinite;
  cursor: pointer;
}
.alert-bar__open {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
  font-size: 14px;
}
@keyframes alert-bar-blink {
  50% {
    filter: brightness(0.82);
  }
}
</style>
