<script setup lang="ts">
import { watchDebounced } from '@vueuse/core'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { IssueStatus } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import IssueCard from '@/components/issues/IssueCard.vue'
import { useStagger } from '@/composables/useMotion'
import { haptic } from '@/max/bridge'
import { useIssuesStore } from '@/stores/issues'
import { ISSUE_STATUSES } from '@/utils/labels'

const store = useIssuesStore()
const route = useRoute()
const router = useRouter()
const list = ref<HTMLElement | null>(null)
const search = ref(store.query)

/** «Просрочено» - не статус сервера, а признак: фильтруем на месте, живёт в адресе (?overdue=1). */
const overdueOnly = computed(() => route.query.overdue === '1')
const items = computed(() =>
  overdueOnly.value ? store.items.filter((i) => i.is_overdue) : store.items,
)
const showSkeleton = computed(() => store.loading && !store.loaded)
const isFiltered = computed(() => !!store.status || !!store.query.trim() || overdueOnly.value)
const showFab = computed(() => !(store.loaded && items.value.length === 0 && !isFiltered.value))

useStagger(list, () => items.value.length)

function setOverdue(on: boolean): void {
  haptic.selection()
  if (on) store.status = null
  void router.replace({ query: on ? { overdue: '1' } : {} })
}

const chips = ref<HTMLElement | null>(null)

onMounted(() => {
  void store.load()
  // Выбранный фильтр мог оказаться за краем ряда (например, пришли по ссылке «Просрочено»)
  void nextTick(() =>
    chips.value
      ?.querySelector('[aria-pressed="true"]')
      ?.scrollIntoView({ inline: 'center', block: 'nearest' }),
  )
})

function setStatus(value: IssueStatus | null): void {
  if (overdueOnly.value) void router.replace({ query: {} })
  if (store.status === value) return
  haptic.selection()
  store.status = value
}

watch(
  () => store.status,
  () => void store.load(),
)
watchDebounced(
  search,
  (value) => {
    store.query = value ?? ''
    void store.load()
  },
  { debounce: 400 },
)
</script>

<template>
  <div class="page">
    <v-text-field
      v-model="search"
      placeholder="Поиск по проблемам"
      prepend-inner-icon="mdi-magnify"
      clearable
      density="comfortable"
      aria-label="Поиск по проблемам"
      class="mb-2"
    />

    <div ref="chips" class="chips-scroll" role="toolbar" aria-label="Фильтр по статусу">
      <v-chip
        v-for="s in ISSUE_STATUSES.slice(0, 2)"
        :key="s.title"
        :color="!overdueOnly && store.status === s.value ? 'primary' : undefined"
        :variant="!overdueOnly && store.status === s.value ? 'flat' : 'outlined'"
        size="large"
        class="filter-chip"
        role="button"
        :aria-pressed="!overdueOnly && store.status === s.value"
        @click="setStatus(s.value)"
      >
        {{ s.title }}
      </v-chip>
      <v-chip
        :color="overdueOnly ? 'deep' : undefined"
        :variant="overdueOnly ? 'flat' : 'outlined'"
        size="large"
        class="filter-chip"
        role="button"
        prepend-icon="mdi-clock-alert-outline"
        :aria-pressed="overdueOnly"
        @click="setOverdue(!overdueOnly)"
      >
        Просрочено
      </v-chip>
      <v-chip
        v-for="s in ISSUE_STATUSES.slice(2)"
        :key="s.title"
        :color="!overdueOnly && store.status === s.value ? 'primary' : undefined"
        :variant="!overdueOnly && store.status === s.value ? 'flat' : 'outlined'"
        size="large"
        class="filter-chip"
        role="button"
        :aria-pressed="!overdueOnly && store.status === s.value"
        @click="setStatus(s.value)"
      >
        {{ s.title }}
      </v-chip>
    </div>

    <v-progress-linear
      v-if="store.loading && store.loaded"
      indeterminate
      color="primary"
      height="3"
      class="my-1"
    />

    <div class="mt-2">
      <ListSkeleton v-if="showSkeleton" />
      <ErrorState
        v-else-if="store.error && items.length === 0"
        :message="store.error"
        :retrying="store.loading"
        @retry="store.load()"
      />
      <EmptyState
        v-else-if="store.loaded && items.length === 0"
        :mood="isFiltered ? 'ok' : 'happy'"
        :title="overdueOnly ? 'Просрочек нет' : isFiltered ? 'Ничего не нашлось' : 'Проблем нет!'"
        :text="
          overdueOnly
            ? 'Все заявки пока в срок. Если что-то затянется, Кузя напомнит'
            : isFiltered
              ? 'Попробуйте другой статус или слова для поиска'
              : 'В доме всё спокойно. Заметили неполадку - сообщите, Кузя поможет'
        "
      >
        <v-btn color="primary" size="large" to="/issues/new" prepend-icon="mdi-plus">
          Сообщить о проблеме
        </v-btn>
      </EmptyState>
      <!-- Нижний отступ, чтобы плавающая кнопка не закрывала последнюю карточку -->
      <div v-else ref="list" class="flex flex-col gap-3 pb-16">
        <div v-for="issue in items" :key="issue.id" data-stagger>
          <IssueCard :issue="issue" />
        </div>
      </div>
    </div>

    <v-btn
      v-if="showFab"
      to="/issues/new"
      color="primary"
      size="large"
      rounded="xl"
      prepend-icon="mdi-plus"
      class="fab"
      aria-label="Сообщить о проблеме"
    >
      Сообщить
    </v-btn>
  </div>
</template>

<style scoped>
.fab {
  position: fixed;
  right: max(16px, calc((100vw - var(--app-max-width)) / 2 + 16px));
  bottom: calc(var(--app-nav-height) + 16px + env(safe-area-inset-bottom));
  z-index: 900;
  box-shadow: 0 8px 24px -6px rgba(var(--v-theme-primary), 0.6);
}
</style>
