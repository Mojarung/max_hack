<script setup lang="ts">
import { ref } from 'vue'
import type { EventOut } from '@/api/types'
import { pop } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { haptic } from '@/max/bridge'
import { useEventsStore } from '@/stores/events'
import { formatDateTime, pluralize } from '@/utils/format'
import { eventKindMeta } from '@/utils/labels'

const props = defineProps<{ event: EventOut; past?: boolean }>()

const store = useEventsStore()
const busy = ref(false)
const button = ref<{ $el: HTMLElement } | null>(null)

async function toggle(): Promise<void> {
  if (busy.value) return
  busy.value = true
  haptic.impact('medium')
  const joining = !props.event.joined_by_me
  try {
    await store.toggleJoin(props.event.id)
    pop(button.value?.$el)
    notify.success(joining ? 'Вы идёте! Кузя напомнит заранее' : 'Отметку сняли')
  } catch (e) {
    notify.error(e, 'Не удалось сохранить')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <article class="card-soft overflow-hidden">
    <router-link
      :to="`/events/${event.id}`"
      class="tap-card flex gap-3 p-3 text-inherit no-underline"
    >
      <div
        class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl"
        :class="`bg-${eventKindMeta(event.kind).color}`"
      >
        <v-icon :icon="eventKindMeta(event.kind).icon" size="30" color="white" />
      </div>
      <div class="min-w-0 flex-1">
        <div class="text-sm font-semibold text-primary">{{ formatDateTime(event.starts_at) }}</div>
        <h3 class="line-clamp-2 my-0.5 text-base leading-snug font-bold">{{ event.title }}</h3>
        <div class="text-muted flex flex-wrap items-center gap-x-3 text-sm">
          <span><v-icon icon="mdi-map-marker-outline" size="16" /> {{ event.place }}</span>
          <span>
            <v-icon icon="mdi-account-multiple-outline" size="16" />
            {{ pluralize(event.participants_count, ['участник', 'участника', 'участников']) }}
            <template v-if="event.max_participants"> из {{ event.max_participants }}</template>
          </span>
        </div>
      </div>
    </router-link>
    <div v-if="!past" class="px-3 pb-3">
      <v-btn
        ref="button"
        block
        size="large"
        :color="event.joined_by_me ? 'success' : 'primary'"
        :variant="event.joined_by_me ? 'tonal' : 'flat'"
        :prepend-icon="event.joined_by_me ? 'mdi-check-circle' : 'mdi-hand-wave-outline'"
        :loading="busy"
        :aria-pressed="event.joined_by_me"
        @click="toggle"
      >
        {{ event.joined_by_me ? 'Иду! Нажмите, если передумали' : 'Иду' }}
      </v-btn>
    </div>
  </article>
</template>
