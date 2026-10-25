<script setup lang="ts">
import { computed, nextTick, onMounted, ref, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { errorMessage } from '@/api/client'
import { safetyApi } from '@/api/endpoints'
import type { RouteOut, ShelterOut } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import { ALERT_INSTRUCTIONS } from '@/components/safety/instructions'
import { useStagger } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { haptic, openLink } from '@/max/bridge'
import { useAlertsStore } from '@/stores/alerts'
import { useSessionStore } from '@/stores/session'
import { formatDistance, formatWalk } from '@/utils/format'
import { locate, type Position } from '@/utils/geo'

const ShelterMap = defineAsyncComponent(() => import('@/components/safety/ShelterMap.vue'))

const session = useSessionStore()
const alerts = useAlertsStore()
const currentRoute = useRoute()

const shelters = ref<ShelterOut[]>([])
const loading = ref(false)
const locating = ref(false)
const error = ref<string | null>(null)
// Откуда считаем: где житель сейчас (если уже искали), иначе дом
const position = ref<Position | null>(alerts.position)
const selectedId = ref<number | null>(null)
const walkRoute = ref<RouteOut | null>(null)
const routeLoading = ref(false)
const routeFailed = ref(false)
const mapRef = ref<InstanceType<typeof ShelterMap> | null>(null)
const list = ref<HTMLElement | null>(null)
const alertBusy = ref(false)

const house = computed(() => session.me?.house)
const canTestAlert = computed(() => session.canUseDevTools || session.isAdmin)
const selected = computed(() => shelters.value.find((s) => s.id === selectedId.value) ?? null)
const origin = computed(() => position.value ?? house.value)

useStagger(list, () => shelters.value.map((s) => s.id).join(','))

async function load(lat?: number, lon?: number): Promise<void> {
  loading.value = true
  error.value = null
  try {
    shelters.value = await safetyApi.shelters(lat ?? origin.value?.lat, lon ?? origin.value?.lon)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

/** Маршрут от текущей точки (или дома) до укрытия; поздний ответ на уже снятый выбор не показываем. */
async function loadRoute(id: number): Promise<void> {
  walkRoute.value = null
  routeFailed.value = false
  routeLoading.value = true
  try {
    const result = await safetyApi.route(id, origin.value?.lat, origin.value?.lon)
    if (selectedId.value === id) walkRoute.value = result
  } catch {
    if (selectedId.value === id) routeFailed.value = true
  } finally {
    if (selectedId.value === id) routeLoading.value = false
  }
}

function select(id: number): void {
  if (selectedId.value !== id) {
    selectedId.value = id
    mapRef.value?.focus(id)
  }
  void loadRoute(id)
}

/** «Маршрут на карте»: выбрать укрытие, построить маршрут и показать карту (она первая на экране). */
function showOnMap(s: ShelterOut): void {
  haptic.impact('light')
  select(s.id)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function scrollToCard(id: number): void {
  document.getElementById(`shelter-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

onMounted(async () => {
  await load()
  // Из экрана тревоги приходим с ?shelter=<id>: сразу выбираем его и рисуем маршрут
  const wanted = Number(currentRoute.query.shelter)
  if (wanted && shelters.value.some((s) => s.id === wanted)) select(wanted)
})

async function findNearest(): Promise<void> {
  if (!house.value) return
  locating.value = true
  haptic.impact('medium')
  try {
    position.value = await locate(house.value)
    await load(position.value.lat, position.value.lon)
    const nearest = shelters.value[0]
    if (!nearest) {
      notify.warning('Укрытий рядом не нашлось')
      return
    }
    select(nearest.id)
    // Ответ «куда идти» должен быть на экране, а не под навигацией
    await nextTick()
    scrollToCard(nearest.id)
    if (position.value.source === 'house') {
      notify.info('Не удалось узнать, где вы', 'Считаем расстояние от дома')
    } else {
      notify.success(`Ближайшее: ${formatDistance(nearest.distance_m)}`, nearest.name)
    }
  } finally {
    locating.value = false
  }
}

function pickFromMap(id: number): void {
  select(id)
  scrollToCard(id)
}

function openYandex(s: ShelterOut): void {
  notify.info('Открываю Яндекс Карты с маршрутом...')
  openLink(s.yandex_url)
}

/** Короткое слово вида для чипа: «паркинг» вместо «подземный паркинг», чтобы чип влезал в карточку. */
const KIND_SHORT: Record<string, string> = {
  shelter: 'укрытие',
  basement: 'подвал',
  parking: 'паркинг',
  underpass: 'переход',
  metro: 'метро',
  bunker: 'бункер',
}

/** Чип источника: «Реестр» у официальных точек, иначе «OpenStreetMap · паркинг». */
function sourceChip(s: ShelterOut): string {
  if (s.official) return 'Реестр'
  return `${s.source_title} · ${KIND_SHORT[s.kind] ?? s.kind_title.toLowerCase()}`
}

async function testAlert(): Promise<void> {
  alertBusy.value = true
  try {
    await alerts.startTest()
  } catch (e) {
    notify.error(e, 'Тревога не запустилась')
  } finally {
    alertBusy.value = false
  }
}

async function endAlert(): Promise<void> {
  alertBusy.value = true
  try {
    await alerts.end()
  } catch (e) {
    notify.error(e, 'Отбой не прошёл')
  } finally {
    alertBusy.value = false
  }
}
</script>

<template>
  <div class="page">
    <v-alert
      v-if="alerts.active"
      type="error"
      variant="flat"
      rounded="xl"
      class="mb-3"
      icon="mdi-alert-octagon"
      :title="alerts.active.kind_title"
    >
      Идёт тревога. Следуйте инструкции и идите в укрытие.
      <template #append>
        <v-btn variant="outlined" color="light" size="small" @click="alerts.minimized = false"
          >Открыть</v-btn
        >
      </template>
    </v-alert>

    <ShelterMap
      v-if="house"
      ref="mapRef"
      :house="house"
      :shelters="shelters"
      :me="position"
      :selected-id="selectedId"
      :route="walkRoute"
      @select="pickFromMap"
    />

    <!-- Сводка маршрута рядом с картой: житель смотрит на линию, а цифры должны быть под рукой -->
    <div v-if="selected" class="route-strip mt-2" aria-live="polite">
      <v-icon icon="mdi-walk" size="22" color="primary" />
      <span class="min-w-0 flex-1">
        <span class="block truncate font-semibold">{{ selected.name }}</span>
        <span v-if="routeLoading" class="text-muted block text-sm">Строим маршрут...</span>
        <span v-else-if="walkRoute" class="block text-sm">
          {{ formatWalk(walkRoute.distance_m, walkRoute.duration_s) }}
          <span v-if="walkRoute.provider === 'straight'" class="text-muted">
            · по прямой, дорога может быть длиннее
          </span>
        </span>
        <span v-else-if="routeFailed" class="text-muted block text-sm">
          Маршрут не построился. Откройте его в Яндекс Картах.
        </span>
      </span>
    </div>

    <v-btn
      block
      size="x-large"
      color="deep"
      :variant="selectedId ? 'tonal' : 'flat'"
      class="mt-3"
      prepend-icon="mdi-crosshairs-gps"
      :loading="locating"
      @click="findNearest"
    >
      Найти ближайшее укрытие
    </v-btn>
    <p v-if="position" class="text-muted mt-2 mb-0 text-center text-sm">
      <template v-if="position.source === 'house'">
        Не удалось узнать, где вы: считаем расстояние от дома.
      </template>
      <template v-else>Расстояние посчитано от того места, где вы сейчас.</template>
    </p>

    <h2 class="section-title">Ближайшие укрытия</h2>
    <ListSkeleton v-if="loading && !shelters.length" :count="3" />
    <ErrorState
      v-else-if="error && !shelters.length"
      :message="error"
      :retrying="loading"
      @retry="load()"
    />
    <EmptyState
      v-else-if="!shelters.length"
      title="Рядом не нашлось укрытий в реестре и на карте"
      text="При тревоге спуститесь в подвал или в помещение без окон."
      mood="worried"
      :size="100"
    >
      <v-btn
        variant="tonal"
        color="primary"
        size="large"
        prepend-icon="mdi-refresh"
        @click="load()"
      >
        Проверить ещё раз
      </v-btn>
    </EmptyState>
    <ol v-else ref="list" class="m-0 flex list-none flex-col gap-3 p-0">
      <li
        v-for="(s, i) in shelters"
        :id="`shelter-${s.id}`"
        :key="s.id"
        class="card-soft p-4"
        :class="{ 'shelter--selected': s.id === selectedId }"
        data-stagger
      >
        <button
          type="button"
          class="shelter-head"
          :aria-pressed="s.id === selectedId"
          @click="pickFromMap(s.id)"
        >
          <span class="shelter-num">{{ i + 1 }}</span>
          <span class="min-w-0 flex-1 text-left">
            <span class="block font-bold leading-snug">{{ s.name }}</span>
            <!-- У объекта OSM без имени название и есть вид: не повторяем «Подземный паркинг» дважды -->
            <span class="text-muted block text-sm">
              <template v-if="s.name !== s.kind_title">{{ s.kind_title }}</template>
              <template v-if="s.address && s.name !== s.kind_title"> · </template>
              <template v-if="s.address">{{ s.address }}</template>
            </span>
          </span>
          <span v-if="s.distance_m !== null" class="shrink-0 text-lg font-bold text-primary">
            {{ formatDistance(s.distance_m) }}
          </span>
        </button>
        <div class="mt-2 ml-11 flex flex-wrap items-center gap-2">
          <v-chip
            size="small"
            variant="tonal"
            :color="s.official ? 'success' : undefined"
            :prepend-icon="s.official ? 'mdi-check-decagram' : 'mdi-map-outline'"
            class="source-chip"
          >
            {{ sourceChip(s) }}
          </v-chip>
          <span v-if="s.capacity" class="text-muted text-sm">до {{ s.capacity }} человек</span>
        </div>

        <div v-if="s.id === selectedId" class="route-info mt-3" aria-live="polite">
          <v-progress-circular v-if="routeLoading" indeterminate size="18" width="2" />
          <v-icon v-else icon="mdi-walk" size="20" color="primary" />
          <span v-if="routeLoading">Строим маршрут...</span>
          <span v-else-if="walkRoute">
            {{ formatWalk(walkRoute.distance_m, walkRoute.duration_s) }}
            <span v-if="walkRoute.provider === 'straight'" class="text-muted">· по прямой</span>
          </span>
          <span v-else-if="routeFailed" class="text-muted">
            Маршрут не построился, откройте в Яндекс Картах
          </span>
        </div>

        <div class="mt-3 flex flex-col gap-2">
          <v-btn
            block
            color="primary"
            :variant="s.id === selectedId ? 'flat' : 'tonal'"
            size="large"
            prepend-icon="mdi-map-marker-path"
            :loading="s.id === selectedId && routeLoading"
            @click="showOnMap(s)"
          >
            Маршрут на карте
          </v-btn>
          <v-btn
            block
            variant="tonal"
            size="large"
            prepend-icon="mdi-open-in-new"
            aria-label="Открыть маршрут пешком в Яндекс Картах"
            @click="openYandex(s)"
          >
            В Яндекс Картах
          </v-btn>
        </div>
      </li>
    </ol>

    <!-- Сначала адреса укрытий, потом инструкция: она раскрыта, читать в стрессе без лишних нажатий -->
    <section class="card-soft rules mt-4" aria-labelledby="rules-title">
      <h2 id="rules-title" class="m-0 flex items-center gap-2 text-base font-bold">
        <v-icon icon="mdi-shield-alert-outline" color="deep" />
        Что делать при тревоге
      </h2>
      <ol class="m-0 flex list-none flex-col gap-2 p-0 pt-2">
        <li v-for="item in ALERT_INSTRUCTIONS" :key="item.text" class="flex items-center gap-3">
          <v-icon :icon="item.icon" color="primary" size="24" />
          <span>{{ item.text }}</span>
        </li>
      </ol>
    </section>

    <section v-if="canTestAlert" class="card-soft mt-6 p-4" aria-label="Проверка оповещения">
      <h3 class="m-0 text-base font-bold">Проверка оповещения (демо)</h3>
      <p class="text-muted mt-1 mb-3 text-sm">
        Все жители увидят экран тревоги в приложении и сообщение Кузи в чате дома.
      </p>
      <div class="flex gap-2">
        <v-btn
          class="flex-1"
          size="large"
          color="error"
          variant="flat"
          prepend-icon="mdi-alarm-light-outline"
          :loading="alertBusy && !alerts.active"
          :disabled="!!alerts.active"
          @click="testAlert"
        >
          Тестовая тревога
        </v-btn>
        <v-btn
          class="flex-1"
          size="large"
          color="success"
          variant="tonal"
          prepend-icon="mdi-check"
          :loading="alertBusy && !!alerts.active"
          :disabled="!alerts.active"
          @click="endAlert"
        >
          Отбой
        </v-btn>
      </div>
    </section>
  </div>
</template>

<style scoped>
.shelter-head {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.shelter-num {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 50%;
  font-weight: 700;
  color: rgb(var(--v-theme-on-primary));
  background: rgb(var(--v-theme-primary));
}
.shelter--selected {
  outline: 3px solid rgb(var(--v-theme-primary));
}
.source-chip {
  max-width: 100%;
  font-size: 14px;
}
.route-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding: 10px 14px;
  border-radius: var(--r-md);
  background: rgb(var(--v-theme-primary) / 0.1);
}
.route-info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
  margin-left: 44px;
  font-weight: 600;
}
.rules {
  padding: 14px 16px;
}
</style>
