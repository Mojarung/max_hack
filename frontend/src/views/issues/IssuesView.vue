<script setup lang="ts">
import { watchDebounced } from '@vueuse/core'
import { computed, onMounted, ref, watch } from 'vue'
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
const list = ref<HTMLElement | null>(null)
const search = ref(store.query)

const showSkeleton = computed(() => store.loading && !store.loaded)
const isFiltered = computed(() => !!store.status || !!store.query.trim())

useStagger(list, () => store.items.length)

onMounted(() => void store.load())

function setStatus(value: IssueStatus | null): void {
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

    <div class="chips-scroll" role="toolbar" aria-label="Фильтр по статусу">
      <v-chip
        v-for="s in ISSUE_STATUSES"
        :key="s.title"
        :color="store.status === s.value ? 'primary' : undefined"
        :variant="store.status === s.value ? 'flat' : 'outlined'"
        size="large"
        :aria-pressed="store.status === s.value"
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
        v-else-if="store.error && store.items.length === 0"
        :message="store.error"
        :retrying="store.loading"
        @retry="store.load()"
      />
      <EmptyState
        v-else-if="store.loaded && store.items.length === 0"
        :mood="isFiltered ? 'ok' : 'happy'"
        :title="isFiltered ? 'Ничего не нашлось' : 'Проблем нет!'"
        :text="
          isFiltered
            ? 'Попробуйте другой статус или слова для поиска'
            : 'В доме всё спокойно. Заметили неполадку - сообщите, Кузя поможет'
        "
      >
        <v-btn color="primary" size="large" to="/issues/new" prepend-icon="mdi-plus">
          Сообщить о проблеме
        </v-btn>
      </EmptyState>
      <div v-else ref="list" class="flex flex-col gap-3">
        <div v-for="issue in store.items" :key="issue.id" data-stagger>
          <IssueCard :issue="issue" />
        </div>
      </div>
    </div>

    <v-btn
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
