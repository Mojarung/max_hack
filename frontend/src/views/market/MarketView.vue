<script setup lang="ts">
import { watchDebounced } from '@vueuse/core'
import { computed, onMounted, ref, watch } from 'vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import ListingCard from '@/components/market/ListingCard.vue'
import { useStagger } from '@/composables/useMotion'
import { haptic } from '@/max/bridge'
import { useListingsStore } from '@/stores/listings'
import { LISTING_CATEGORY_ICONS } from '@/utils/labels'

const store = useListingsStore()
const grid = ref<HTMLElement | null>(null)
const search = ref(store.query)

const isFiltered = computed(() => !!store.category || store.freeOnly || !!store.query.trim())

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
  () => [store.category, store.freeOnly],
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
      placeholder="Что ищете?"
      prepend-inner-icon="mdi-magnify"
      clearable
      density="comfortable"
      aria-label="Поиск по объявлениям"
      class="mb-2"
    />

    <div class="chips-scroll" role="toolbar" aria-label="Категории">
      <v-chip
        size="large"
        :color="store.freeOnly ? 'secondary' : undefined"
        :variant="store.freeOnly ? 'flat' : 'outlined'"
        prepend-icon="mdi-gift-outline"
        :aria-pressed="store.freeOnly"
        @click="store.freeOnly = !store.freeOnly"
      >
        Даром
      </v-chip>
      <v-chip
        size="large"
        :color="!store.category ? 'primary' : undefined"
        :variant="!store.category ? 'flat' : 'outlined'"
        :aria-pressed="!store.category"
        @click="pickCategory(null)"
      >
        Все
      </v-chip>
      <v-chip
        v-for="c in store.categories"
        :key="c.code"
        size="large"
        :color="store.category === c.code ? 'primary' : undefined"
        :variant="store.category === c.code ? 'flat' : 'outlined'"
        :prepend-icon="LISTING_CATEGORY_ICONS[c.code]"
        :aria-pressed="store.category === c.code"
        @click="pickCategory(c.code)"
      >
        {{ c.title }}
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
      <ListSkeleton v-if="store.loading && !store.loaded" variant="grid" :count="6" />
      <ErrorState
        v-else-if="store.error && store.items.length === 0"
        :message="store.error"
        :retrying="store.loading"
        @retry="store.load()"
      />
      <EmptyState
        v-else-if="store.loaded && store.items.length === 0"
        :title="isFiltered ? 'Ничего не нашлось' : 'Пока пусто'"
        :text="
          isFiltered
            ? 'Попробуйте другую категорию или слова'
            : 'Отдайте ненужное соседям или продайте: Кузя расскажет всему дому'
        "
      >
        <v-btn color="primary" size="large" to="/market/new" prepend-icon="mdi-plus"
          >Разместить</v-btn
        >
      </EmptyState>
      <div v-else ref="grid" class="grid grid-cols-2 gap-3">
        <div v-for="listing in store.items" :key="listing.id" data-stagger class="flex">
          <ListingCard :listing="listing" class="w-full" />
        </div>
      </div>
    </div>

    <v-btn
      to="/market/new"
      color="primary"
      size="large"
      rounded="xl"
      prepend-icon="mdi-plus"
      class="fab"
    >
      Разместить
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
