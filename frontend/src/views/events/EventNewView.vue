<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { EventKind } from '@/api/types'
import { useDirtyGuard } from '@/composables/useDirtyGuard'
import { notify } from '@/lib/notify'
import { haptic } from '@/max/bridge'
import { useEventsStore } from '@/stores/events'
import { EVENT_KINDS } from '@/utils/labels'

const router = useRouter()
const store = useEventsStore()

function isoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const tomorrow = new Date(Date.now() + 24 * 3600 * 1000)
const title = ref('')
const kind = ref<EventKind>('subbotnik')
const date = ref(isoDate(tomorrow))
const time = ref('11:00')
const place = ref('')
const description = ref('')
const limited = ref(false)
const maxParticipants = ref<string>('')
const saving = ref(false)
const done = ref(false)
const showErrors = ref(false)

const startsAt = computed(() => {
  const d = new Date(`${date.value}T${time.value || '00:00'}`)
  return Number.isNaN(d.getTime()) ? null : d
})
const limit = computed(() => Number(maxParticipants.value))
const errors = computed(() => ({
  title: title.value.trim().length < 3 ? 'Как назовём событие?' : '',
  when: !startsAt.value
    ? 'Укажите дату и время'
    : startsAt.value.getTime() < Date.now()
      ? 'Время уже прошло, выберите будущее'
      : '',
  place: place.value.trim().length < 2 ? 'Где собираемся?' : '',
  limit:
    limited.value && (!Number.isInteger(limit.value) || limit.value < 2)
      ? 'Минимум 2 участника'
      : '',
}))
const valid = computed(() => Object.values(errors.value).every((e) => !e))
const dirty = computed(() => !done.value && (!!title.value || !!place.value || !!description.value))
useDirtyGuard(dirty)

function pickKind(value: EventKind): void {
  kind.value = value
  haptic.selection()
  if (!title.value) {
    const suggestions: Partial<Record<EventKind, string>> = {
      subbotnik: 'Субботник во дворе',
      meeting: 'Собрание жильцов',
      holiday: 'Праздник двора',
    }
    title.value = suggestions[value] ?? ''
  }
}

async function submit(): Promise<void> {
  showErrors.value = true
  if (!valid.value || !startsAt.value) {
    notify.warning('Проверьте поля формы')
    return
  }
  saving.value = true
  try {
    const event = await store.create({
      title: title.value.trim(),
      description: description.value.trim(),
      kind: kind.value,
      starts_at: startsAt.value.toISOString(),
      place: place.value.trim(),
      max_participants: limited.value ? limit.value : null,
    })
    done.value = true
    notify.success('Событие создано', 'Кузя позовёт соседей в чате дома')
    await router.replace(`/events/${event.id}`)
  } catch (e) {
    notify.error(e, 'Не удалось создать событие')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page">
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <section>
        <h2 class="mt-0 mb-2 text-base font-bold">Что за событие?</h2>
        <div class="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Тип события">
          <button
            v-for="k in EVENT_KINDS"
            :key="k.value"
            type="button"
            role="radio"
            :aria-checked="kind === k.value"
            class="kind"
            :class="{ 'kind--on': kind === k.value }"
            @click="pickKind(k.value)"
          >
            <v-icon :icon="k.icon" size="28" />
            <span>{{ k.title }}</span>
          </button>
        </div>
      </section>

      <v-text-field
        v-model="title"
        label="Название"
        placeholder="Осенний субботник"
        maxlength="120"
        :error-messages="showErrors ? errors.title : ''"
      />

      <div class="grid grid-cols-2 gap-3">
        <v-text-field v-model="date" type="date" label="Дата" :min="isoDate(new Date())" />
        <v-text-field v-model="time" type="time" label="Время" step="300" />
      </div>
      <p v-if="showErrors && errors.when" class="m-0 -mt-2 text-sm text-error" role="alert">
        {{ errors.when }}
      </p>

      <v-text-field
        v-model="place"
        label="Место"
        placeholder="Двор, у детской площадки"
        prepend-inner-icon="mdi-map-marker-outline"
        maxlength="200"
        :error-messages="showErrors ? errors.place : ''"
      />

      <v-textarea
        v-model="description"
        label="Подробности"
        placeholder="Что взять с собой, кто за что отвечает"
        rows="3"
        auto-grow
        maxlength="2000"
        counter="2000"
      />

      <div class="card-soft px-4 py-2">
        <v-switch
          v-model="limited"
          color="primary"
          inset
          hide-details
          label="Ограничить число участников"
        />
        <v-text-field
          v-if="limited"
          v-model="maxParticipants"
          label="Сколько человек максимум"
          inputmode="numeric"
          class="mb-2"
          :error-messages="showErrors ? errors.limit : ''"
        />
      </div>

      <v-btn
        type="submit"
        block
        class="sticky-cta"
        size="x-large"
        color="primary"
        prepend-icon="mdi-calendar-check"
        :loading="saving"
      >
        Создать событие
      </v-btn>
    </form>
  </div>
</template>

<style scoped>
.kind {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 76px;
  padding: 8px 4px;
  border-radius: 16px;
  border: 1.5px solid rgba(var(--v-border-color), 0.2);
  background: rgb(var(--v-theme-surface));
  color: inherit;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;
}
.kind--on {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}
.kind:focus-visible {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
</style>
