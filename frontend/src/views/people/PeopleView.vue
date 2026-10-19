<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { errorMessage } from '@/api/client'
import { peopleApi } from '@/api/endpoints'
import type { Neighbour } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import SegmentedControl from '@/components/common/SegmentedControl.vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import { useStagger } from '@/composables/useMotion'
import { fullName } from '@/utils/format'

const items = ref<Neighbour[]>([])
const loading = ref(false)
const loaded = ref(false)
const error = ref<string | null>(null)
const query = ref('')
const list = ref<HTMLElement | null>(null)
const role = ref<'all' | 'admin'>('all')
const admins = computed(() => items.value.filter((p) => p.role === 'admin').length)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const byRole =
    role.value === 'admin' ? items.value.filter((p) => p.role === 'admin') : items.value
  if (!q) return byRole
  return byRole.filter((p) =>
    `${p.first_name} ${p.last_name} ${p.apartment ?? ''}`.toLowerCase().includes(q),
  )
})
useStagger(list, () => filtered.value.length)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    items.value = await peopleApi.list()
    loaded.value = true
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="page">
    <v-text-field
      v-model="query"
      placeholder="Имя или квартира"
      prepend-inner-icon="mdi-magnify"
      clearable
      density="comfortable"
      aria-label="Поиск соседей"
      class="mb-3"
    />
    <SegmentedControl
      v-if="admins"
      v-model="role"
      class="mb-3"
      label="Кого показать"
      :options="[
        { value: 'all', label: `Все ${items.length}` },
        { value: 'admin', label: `Администраторы ${admins}` },
      ]"
    />
    <ListSkeleton v-if="loading && !loaded" :count="5" />
    <ErrorState v-else-if="error" :message="error" :retrying="loading" @retry="load" />
    <EmptyState
      v-else-if="loaded && !filtered.length"
      title="Никого не нашли"
      text="Соседи появляются здесь, когда пишут в чат дома или открывают приложение"
    />
    <ul v-else ref="list" class="group-list m-0 list-none p-0" style="--group-inset: 68px">
      <li v-for="p in filtered" :key="p.id" data-stagger>
        <router-link
          :to="`/people/${p.id}`"
          class="tap-row flex items-center gap-3 p-3 text-inherit no-underline"
        >
          <UserAvatar :user="p" :size="44" />
          <span class="min-w-0 flex-1">
            <span class="line-clamp-2 leading-snug font-semibold">{{ fullName(p) }}</span>
            <span v-if="p.role === 'admin'" class="role-badge">
              <v-icon icon="mdi-shield-account" size="16" aria-hidden="true" />
              администратор
            </span>
            <span class="text-muted block text-sm">
              <template v-if="p.apartment">кв. {{ p.apartment }} · </template>{{ p.level_title }}
            </span>
          </span>

          <v-icon icon="mdi-chevron-right" aria-hidden="true" />
        </router-link>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.role-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 2px 0;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 600;
  color: rgb(var(--v-theme-on-primary-container));
  background: rgb(var(--v-theme-primary-container));
}
</style>
