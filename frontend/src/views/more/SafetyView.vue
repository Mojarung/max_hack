<script setup lang="ts">
import { computed, onMounted, ref, defineAsyncComponent } from 'vue'
import { errorMessage } from '@/api/client'
import { safetyApi } from '@/api/endpoints'
import type { ShelterOut } from '@/api/types'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import { useStagger } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { haptic, openLink } from '@/max/bridge'
import { useAlertsStore } from '@/stores/alerts'
import { useSessionStore } from '@/stores/session'
import { formatDistance } from '@/utils/format'
import { locate, type Position } from '@/utils/geo'

const ShelterMap = defineAsyncComponent(() => import('@/components/safety/ShelterMap.vue'))

const session = useSessionStore()
const alerts = useAlertsStore()

const shelters = ref<ShelterOut[]>([])
const loading = ref(false)
const locating = ref(false)
const error = ref<string | null>(null)
const position = ref<Position | null>(null)
const selectedId = ref<number | null>(null)
const mapRef = ref<InstanceType<typeof ShelterMap> | null>(null)
const list = ref<HTMLElement | null>(null)
const alertBusy = ref(false)

const house = computed(() => session.me?.house)
const canTestAlert = computed(() => session.canUseDevTools || session.isAdmin)

useStagger(list, () => shelters.value.map((s) => s.id).join(','))

async function load(lat?: number, lon?: number): Promise<void> {
  loading.value = true
  error.value = null
  try {
    shelters.value = await safetyApi.shelters(lat ?? house.value?.lat, lon ?? house.value?.lon)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

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
    selectedId.value = nearest.id
    mapRef.value?.focus(nearest.id)
    if (position.value.source === 'house') {
      notify.info('Не удалось узнать, где вы', 'Считаем расстояние от дома')
    } else {
      notify.success(`Ближайшее: ${formatDistance(nearest.distance_m)}`, nearest.name)
    }
  } finally {
    locating.value = false
  }
}

function select(id: number): void {
  selectedId.value = id
  mapRef.value?.focus(id)
  document.getElementById(`shelter-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
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
      @select="select"
    />

    <v-btn
      block
      size="x-large"
      color="error"
      class="mt-3"
      prepend-icon="mdi-crosshairs-gps"
      :loading="locating"
      @click="findNearest"
    >
      Найти ближайшее укрытие
    </v-btn>
    <p class="text-muted mt-2 mb-0 text-center text-sm">
      Разрешите доступ к геопозиции. Если не получится, посчитаем от дома.
    </p>

    <h2 class="section-title">Укрытия рядом</h2>
    <ListSkeleton v-if="loading && !shelters.length" :count="3" />
    <ErrorState
      v-else-if="error && !shelters.length"
      :message="error"
      :retrying="loading"
      @retry="load()"
    />
    <p v-else-if="!shelters.length" class="text-muted">Укрытия в базе пока не добавлены.</p>
    <ol v-else ref="list" class="m-0 flex list-none flex-col gap-3 p-0">
      <li
        v-for="(s, i) in shelters"
        :id="`shelter-${s.id}`"
        :key="s.id"
        class="card-soft p-4"
        :class="{ 'shelter--selected': s.id === selectedId }"
        data-stagger
      >
        <button type="button" class="shelter-head" @click="select(s.id)">
          <span class="shelter-num">{{ i + 1 }}</span>
          <span class="min-w-0 flex-1 text-left">
            <span class="block font-bold leading-snug">{{ s.name }}</span>
            <span class="text-muted block text-sm">{{ s.address }}</span>
          </span>
          <span v-if="s.distance_m !== null" class="shrink-0 text-lg font-bold text-primary">
            {{ formatDistance(s.distance_m) }}
          </span>
        </button>
        <div v-if="s.capacity" class="text-muted mt-1 ml-11 text-sm">
          Вместимость: до {{ s.capacity }} человек
        </div>
        <div class="mt-3 flex gap-2">
          <v-btn
            class="flex-1"
            color="primary"
            size="large"
            prepend-icon="mdi-walk"
            @click="openLink(s.yandex_url)"
          >
            Маршрут в Яндекс Картах
          </v-btn>
          <v-btn
            variant="tonal"
            size="large"
            aria-label="Открыть в OpenStreetMap"
            @click="openLink(s.osm_url)"
          >
            OSM
          </v-btn>
        </div>
      </li>
    </ol>

    <section v-if="canTestAlert" class="card-soft mt-6 p-4" aria-label="Проверка оповещения">
      <h3 class="m-0 text-base font-bold">Проверка оповещения (демо)</h3>
      <p class="text-muted mt-1 mb-3 text-sm">
        Все жители увидят экран тревоги в приложении и сообщение Кузи в чате дома.
      </p>
      <div class="flex gap-2">
        <v-btn
          class="flex-1"
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
  color: #caf0f8;
  background: rgb(var(--v-theme-secondary));
}
.shelter--selected {
  outline: 3px solid rgb(var(--v-theme-error));
}
</style>
