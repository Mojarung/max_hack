<script setup lang="ts">
import AppFab from '@/components/common/AppFab.vue'
import { useSessionStorage } from '@vueuse/core'
import { computed, ref, watch } from 'vue'
import AnimatedList from '@/components/common/AnimatedList.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import RefreshBar from '@/components/common/RefreshBar.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import SegmentedControl from '@/components/common/SegmentedControl.vue'
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
    <SegmentedControl
      v-model="scope"
      class="mb-3"
      label="Какие события показать"
      :options="[
        { value: 'upcoming', label: 'Скоро' },
        { value: 'past', label: 'Прошедшие' },
      ]"
    />

    <RefreshBar :active="state.loading && state.loaded" />

    <div class="list-area">
      <Transition name="swap" mode="out-in">
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
          :text="
            scope === 'upcoming' ? 'Предложите субботник, праздник двора или собрание' : undefined
          "
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
        <div v-else ref="list">
          <AnimatedList class="flex flex-col gap-3">
            <div v-for="event in state.items" :key="event.id" data-stagger>
              <EventCard :event="event" :past="scope === 'past'" />
            </div>
          </AnimatedList>
        </div>
      </Transition>
    </div>
    <AppFab icon="mdi-plus" label="Создать событие" to="/events/new" />
  </div>
</template>
