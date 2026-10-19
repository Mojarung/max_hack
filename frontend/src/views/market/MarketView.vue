<script setup lang="ts">
import AppFab from '@/components/common/AppFab.vue'
import { watchDebounced } from '@vueuse/core'
import { computed, onMounted, ref, watch } from 'vue'
import AnimatedList from '@/components/common/AnimatedList.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import RefreshBar from '@/components/common/RefreshBar.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import SegmentedControl from '@/components/common/SegmentedControl.vue'
import ListingCard from '@/components/market/ListingCard.vue'
import { useStagger } from '@/composables/useMotion'
import { haptic } from '@/max/bridge'
import { useListingsStore } from '@/stores/listings'
import { LISTING_CATEGORY_ICONS } from '@/utils/labels'

const store = useListingsStore()
const grid = ref<HTMLElement | null>(null)
const search = ref(store.query)

const isFiltered = computed(
  () => !!store.category || store.freeOnly || !!store.query.trim() || store.scope !== 'active',
)
const SCOPES = [
  { value: 'active', title: 'В продаже', icon: 'mdi-storefront-outline' },
  { value: 'mine', title: 'Мои', icon: 'mdi-account-outline' },
  { value: 'closed', title: 'Закрытые', icon: 'mdi-archive-outline' },
] as const
const emptyText = computed(() => {
  if (store.scope === 'mine')
    return 'Вы ещё ничего не размещали. Закрытые объявления тоже будут здесь'
  if (store.scope === 'closed')
    return 'Когда соседи отдадут или продадут вещи, объявления появятся здесь'
  return isFiltered.value
    ? 'Попробуйте другую категорию или слова'
    : 'Отдайте ненужное соседям или продайте: Кузя расскажет всему дому'
})

useStagger(grid, () => store.items.length)

onMounted(() => {
  void store.loadCategories()
  void store.load()
})

function pickCategory(code: string | null): void {
  haptic.selection()
  store.category = store.category === code ? null : code
}

watch(
  () => [store.category, store.freeOnly, store.scope],
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
  <div class="page page--with-fab">
    <v-text-field
      v-model="search"
      placeholder="Что ищете?"
      prepend-inner-icon="mdi-magnify"
      clearable
      density="comfortable"
      aria-label="Поиск по объявлениям"
      class="mb-2"
    />

    <SegmentedControl
      v-model="store.scope"
      class="mb-2"
      label="Какие объявления показать"
      :options="SCOPES.map((s) => ({ value: s.value, label: s.title }))"
    />

    <div class="chips-scroll" role="toolbar" aria-label="Категории">
      <v-chip
        size="large"
        class="filter-chip"
        role="button"
        :color="!store.category ? 'primary' : undefined"
        :variant="!store.category ? 'flat' : 'outlined'"
        :aria-pressed="!store.category"
        @click="pickCategory(null)"
      >
        Все
      </v-chip>
      <v-chip
        size="large"
        class="filter-chip"
        role="button"
        :color="store.freeOnly ? 'primary' : undefined"
        :variant="store.freeOnly ? 'flat' : 'outlined'"
        prepend-icon="mdi-gift-outline"
        :aria-pressed="store.freeOnly"
        @click="store.freeOnly = !store.freeOnly"
      >
        Только даром
      </v-chip>
      <v-chip
        v-for="c in store.categories"
        :key="c.code"
        size="large"
        class="filter-chip"
        role="button"
        :color="store.category === c.code ? 'primary' : undefined"
        :variant="store.category === c.code ? 'flat' : 'outlined'"
        :prepend-icon="LISTING_CATEGORY_ICONS[c.code]"
        :aria-pressed="store.category === c.code"
        @click="pickCategory(c.code)"
      >
        {{ c.title }}
      </v-chip>
    </div>

    <RefreshBar :active="store.loading && store.loaded" />

    <div class="list-area mt-1">
      <Transition name="swap" mode="out-in">
        <ListSkeleton v-if="store.loading && !store.loaded" variant="grid" :count="6" />
        <ErrorState
          v-else-if="store.error && store.items.length === 0"
          :message="store.error"
          :retrying="store.loading"
          @retry="store.load()"
        />
        <EmptyState
          v-else-if="store.loaded && store.items.length === 0"
          :title="isFiltered && store.scope === 'active' ? 'Ничего не нашлось' : 'Пока пусто'"
          :text="emptyText"
        >
          <v-btn color="primary" size="large" to="/market/new" prepend-icon="mdi-plus"
            >Отдать или продать</v-btn
          >
        </EmptyState>
        <div v-else ref="grid">
          <AnimatedList class="grid grid-cols-2 gap-3">
            <div v-for="listing in store.items" :key="listing.id" data-stagger class="flex">
              <ListingCard :listing="listing" class="w-full" />
            </div>
          </AnimatedList>
        </div>
      </Transition>
    </div>

    <AppFab icon="mdi-plus" label="Отдать или продать" to="/market/new" />
  </div>
</template>

<style scoped></style>
