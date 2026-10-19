<script setup lang="ts">
import { watchDebounced } from '@vueuse/core'
import { computed, onMounted, ref } from 'vue'
import { ApiError, errorMessage } from '@/api/client'
import { issuesApi, searchApi } from '@/api/endpoints'
import type { IssueOut, SearchOut } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import IssueCard from '@/components/issues/IssueCard.vue'
import ListingCard from '@/components/market/ListingCard.vue'
import { useStagger } from '@/composables/useMotion'
import { formatDateTime } from '@/utils/format'
import { eventKindMeta } from '@/utils/labels'

const query = ref('')
const result = ref<SearchOut | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const input = ref<{ focus: () => void } | null>(null)
const box = ref<HTMLElement | null>(null)
let controller: AbortController | null = null

const total = computed(() =>
  result.value
    ? result.value.issues.length + result.value.events.length + result.value.listings.length
    : 0,
)
const SUGGESTIONS = ['лифт', 'крыша', 'коляска', 'субботник', 'шум']

useStagger(box, () => total.value)
/** До ввода показываем, что сейчас происходит в доме: заявки, которым нужны голоса. */
const now = ref<IssueOut[]>([])
onMounted(() => {
  input.value?.focus()
  issuesApi
    .list({ status: 'voting' })
    .then((list) => (now.value = list.slice(0, 3)))
    .catch(() => (now.value = []))
})

async function run(q: string): Promise<void> {
  controller?.abort()
  const trimmed = q.trim()
  if (trimmed.length < 2) {
    result.value = null
    error.value = null
    return
  }
  const current = new AbortController()
  controller = current
  loading.value = true
  error.value = null
  try {
    result.value = await searchApi.search(trimmed, current.signal)
  } catch (e) {
    if (e instanceof ApiError && e.kind === 'aborted') return
    error.value = errorMessage(e)
  } finally {
    if (controller === current) loading.value = false
  }
}

watchDebounced(query, (q) => void run(q ?? ''), { debounce: 400 })
</script>

<template>
  <div class="page">
    <v-text-field
      ref="input"
      v-model="query"
      placeholder="Лифт, коляска, субботник..."
      prepend-inner-icon="mdi-magnify"
      clearable
      :loading="loading"
      aria-label="Поиск по дому"
    />
    <div v-if="!query" class="tags mt-3">
      <v-chip
        v-for="s in SUGGESTIONS"
        :key="s"
        size="large"
        variant="outlined"
        @click="query = s"
        >{{ s }}</v-chip
      >
    </div>

    <div class="mt-3">
      <ListSkeleton v-if="loading && !result" :count="3" />
      <p v-else-if="error" class="text-error" role="alert">{{ error }}</p>
      <EmptyState
        v-else-if="result && total === 0"
        title="Ничего не нашлось"
        text="Попробуйте другие слова"
        mood="worried"
      />
      <div v-else-if="result" ref="box" aria-live="polite">
        <template v-if="result.issues.length">
          <h2 class="section-title">Заявки · {{ result.issues.length }}</h2>
          <div class="flex flex-col gap-3">
            <div v-for="i in result.issues" :key="`i${i.id}`" data-stagger>
              <IssueCard :issue="i" />
            </div>
          </div>
        </template>
        <template v-if="result.events.length">
          <h2 class="section-title">События · {{ result.events.length }}</h2>
          <div class="flex flex-col gap-2">
            <router-link
              v-for="e in result.events"
              :key="`e${e.id}`"
              :to="`/events/${e.id}`"
              class="card-soft tap-card flex items-center gap-3 p-3 text-inherit no-underline"
              data-stagger
            >
              <v-avatar :color="eventKindMeta(e.kind).color" rounded="lg">
                <v-icon :icon="eventKindMeta(e.kind).icon" />
              </v-avatar>
              <div class="min-w-0">
                <div class="font-semibold">{{ e.title }}</div>
                <div class="text-muted text-sm">
                  {{ formatDateTime(e.starts_at) }} · {{ e.place }}
                </div>
              </div>
            </router-link>
          </div>
        </template>
        <template v-if="result.listings.length">
          <h2 class="section-title">Вещи соседей · {{ result.listings.length }}</h2>
          <div class="grid grid-cols-2 gap-3">
            <div v-for="l in result.listings" :key="`l${l.id}`" data-stagger class="flex">
              <ListingCard :listing="l" class="w-full" />
            </div>
          </div>
        </template>
      </div>
      <template v-else>
        <p class="text-muted mt-1 mb-0 text-sm">Ищем сразу по заявкам, событиям и вещам соседей.</p>
        <template v-if="now.length">
          <h2 class="section-title">Нужны голоса</h2>
          <div class="flex flex-col gap-3">
            <IssueCard v-for="i in now" :key="i.id" :issue="i" />
          </div>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
