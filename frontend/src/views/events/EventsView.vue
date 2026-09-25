<script setup lang="ts">
import { useSessionStorage } from '@vueuse/core'
import { computed, ref, watch } from 'vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import EventCard from '@/components/events/EventCard.vue'
import { useStagger } from '@/composables/useMotion'
import { useEventsStore, type EventScope } from '@/stores/events'

const store = useEventsStore()
const scope = useSessionStorage<EventScope>('kuzya.eventsScope', 'upcoming')
const list = ref<HTMLElement | null>(null)
const state = computed(() => store.scopes[scope.value])

useStagger(list, () => `${scope.value}:${state.value.items.length}`)

watch(scope, (value) => void store.load(value), { immediate: true })
</script>

<template>
  <div class="page page--with-fab">
    <v-tabs v-model="scope" grow color="primary" class="mb-3" aria-label="Какие события показать">
      <v-tab value="upcoming" class="!text-base">Скоро</v-tab>
      <v-tab value="past" class="!text-base">Прошедшие</v-tab>
    </v-tabs>

    <v-progress-linear
      v-if="state.loading && state.loaded"
      indeterminate
      color="primary"
      height="3"
      class="mb-2"
    />

    <ListSkeleton v-if="state.loading && !state.loaded" :count="3" />
    <ErrorState
      v-else-if="state.error && state.items.length === 0"
      :message="state.error"
      :retrying="state.loading"
      @retry="store.load(scope)"
    />
    <EmptyState
      v-else-if="state.loaded && state.items.length === 0"
      :title="scope === 'upcoming' ? 'Пока ничего не запланировано' : 'Прошедших событий нет'"
      :text="scope === 'upcoming' ? 'Предложите субботник, праздник двора или собрание' : undefined"
    >
      <v-btn
        v-if="scope === 'upcoming'"
        color="primary"
        size="large"
        to="/events/new"
        prepend-icon="mdi-plus"
      >
        Создать событие
      </v-btn>
    </EmptyState>
    <div v-else ref="list" class="flex flex-col gap-3">
      <div v-for="event in state.items" :key="event.id" data-stagger>
        <EventCard :event="event" :past="scope === 'past'" />
      </div>
    </div>

    <v-btn
      to="/events/new"
      color="primary"
      size="large"
      rounded="xl"
      prepend-icon="mdi-plus"
      class="fab"
    >
      Создать событие
    </v-btn>
  </div>
</template>
