<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { issuesApi } from '@/api/endpoints'
import type { IssueOut } from '@/api/types'
import AnimatedNumber from '@/components/common/AnimatedNumber.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import HealthRing from '@/components/common/HealthRing.vue'
import EventCard from '@/components/events/EventCard.vue'
import IssueCard from '@/components/issues/IssueCard.vue'
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import { Skeleton } from '@/components/ui/skeleton'
import { pageEnter, pageLeave, staggerIn } from '@/composables/useMotion'
import { hasNumericId, onRealtime } from '@/realtime/sse'
import { useEventsStore } from '@/stores/events'
import { usePulseStore } from '@/stores/pulse'
import { useSessionStore } from '@/stores/session'
import { MOOD_TITLES } from '@/utils/labels'

const session = useSessionStore()
const pulseStore = usePulseStore()
const events = useEventsStore()

const root = ref<HTMLElement | null>(null)
const votingIssues = ref<IssueOut[]>([])
const phraseKey = ref(0)

const pulse = computed(() => pulseStore.pulse)
const user = computed(() => session.me?.user)
const nextEvent = computed(() => events.scopes.upcoming.items[0] ?? null)
const xpPercent = computed(() =>
  pulse.value && pulse.value.xp_next > 0
    ? Math.min(100, (pulse.value.xp / pulse.value.xp_next) * 100)
    : 0,
)
const userProgress = computed(() => {
  const u = user.value
  if (!u || !u.next_level_points) return 100
  return Math.min(100, (u.points / u.next_level_points) * 100)
})

/** «Горячая» проблема: та, которой меньше всего голосов до порога. */
const hotIssue = computed(() => {
  const candidates = votingIssues.value.filter(
    (i) => i.status === 'voting' && i.votes_needed > 0 && i.votes_count < i.votes_needed,
  )
  return (
    [...candidates].sort(
      (a, b) => b.votes_count / b.votes_needed - a.votes_count / a.votes_needed,
    )[0] ?? null
  )
})

const tiles = computed(() => {
  const s = pulse.value?.stats
  return [
    {
      key: 'issues',
      title: 'Открытых проблем',
      value: s?.open_issues ?? 0,
      icon: 'mdi-alert-circle-outline',
      to: '/issues',
      color: 'warning',
    },
    {
      key: 'events',
      title: 'Ближайших событий',
      value: s?.upcoming_events ?? 0,
      icon: 'mdi-calendar-star',
      to: '/events',
      color: 'secondary',
    },
    {
      key: 'market',
      title: 'Объявлений',
      value: s?.active_listings ?? 0,
      icon: 'mdi-storefront-outline',
      to: '/market',
      color: 'primary',
    },
    {
      key: 'overdue',
      title: 'Просрочено',
      value: s?.overdue_issues ?? 0,
      icon: 'mdi-clock-alert-outline',
      to: '/issues',
      color: (s?.overdue_issues ?? 0) > 0 ? 'error' : 'success',
    },
  ]
})

async function loadVoting(): Promise<void> {
  try {
    votingIssues.value = await issuesApi.list({ status: 'voting' })
  } catch {
    votingIssues.value = []
  }
}

const offCreated = onRealtime('issue.created', () => void loadVoting())
const offUpdated = onRealtime('issue.updated', (data) => {
  if (!hasNumericId(data)) return
  const issue = data as IssueOut
  votingIssues.value = votingIssues.value.map((i) =>
    i.id === issue.id ? { ...i, ...issue, voted_by_me: i.voted_by_me } : i,
  )
})
onBeforeUnmount(() => {
  offCreated()
  offUpdated()
})

onMounted(() => {
  if (!pulseStore.pulse) void pulseStore.load()
  if (!events.scopes.upcoming.loaded) void events.load('upcoming')
  void loadVoting()
})

watch(
  () => [pulse.value, hotIssue.value, nextEvent.value],
  () => requestAnimationFrame(() => staggerIn(root.value)),
  { immediate: true, flush: 'post' },
)
watch(
  () => pulse.value?.phrase,
  () => (phraseKey.value += 1),
)
</script>

<template>
  <div ref="root" class="page">
    <ErrorState
      v-if="pulseStore.error && !pulse"
      :message="pulseStore.error"
      :retrying="pulseStore.loading"
      @retry="pulseStore.load()"
    />

    <template v-else>
      <!-- Кузя и его фраза -->
      <section class="hero card-soft" data-stagger>
        <div class="flex items-end gap-2">
          <KuzyaMascot :mood="pulse?.mood ?? 'ok'" :size="128" class="shrink-0" />
          <div class="bubble" aria-live="polite">
            <Transition :css="false" mode="out-in" @enter="pageEnter" @leave="pageLeave">
              <p :key="phraseKey" class="m-0">
                <template v-if="pulse">{{ pulse.phrase }}</template>
                <template v-else>Сейчас посмотрю, как дела у дома...</template>
              </p>
            </Transition>
          </div>
        </div>
      </section>

      <!-- Житель -->
      <router-link
        v-if="user"
        to="/more/achievements"
        class="card-soft tap-card mt-3 flex items-center gap-3 p-3 text-inherit no-underline"
        data-stagger
        aria-label="Мой уровень и ачивки"
      >
        <v-avatar color="primary" size="44">
          <span class="text-lg font-bold">{{ user.level }}</span>
        </v-avatar>
        <div class="min-w-0 flex-1">
          <div class="font-semibold">{{ user.first_name }}, вы «{{ user.level_title }}»</div>
          <v-progress-linear
            :model-value="userProgress"
            color="primary"
            height="8"
            class="my-1.5"
          />
          <div class="text-muted text-sm">
            <AnimatedNumber :value="user.points" /> очков
            <template v-if="user.next_level_points">
              · до нового уровня {{ user.next_level_points - user.points }}</template
            >
          </div>
        </div>
        <v-icon icon="mdi-chevron-right" />
      </router-link>

      <!-- Здоровье дома -->
      <section
        class="card-soft mt-3 flex items-center gap-4 p-4"
        data-stagger
        aria-label="Здоровье дома"
      >
        <HealthRing v-if="pulse" :score="pulse.score" :size="104" />
        <Skeleton v-else class="h-[104px] w-[104px] rounded-full" />
        <div class="min-w-0 flex-1">
          <h2 class="m-0 text-lg font-bold">Здоровье дома</h2>
          <div class="text-muted text-sm">{{ pulse ? MOOD_TITLES[pulse.mood] : 'Считаем...' }}</div>
          <div class="mt-3 flex items-baseline justify-between text-sm">
            <span class="font-semibold">Дом: уровень {{ pulse?.level ?? '...' }}</span>
            <span class="text-muted tabular-nums"
              >{{ pulse?.xp ?? 0 }} / {{ pulse?.xp_next ?? 0 }} XP</span
            >
          </div>
          <v-progress-linear :model-value="xpPercent" color="secondary" height="10" class="mt-1" />
        </div>
      </section>

      <!-- Показатели -->
      <section class="mt-3 grid grid-cols-2 gap-3" aria-label="Коротко о доме">
        <router-link
          v-for="tile in tiles"
          :key="tile.key"
          :to="tile.to"
          class="card-soft tap-card flex flex-col gap-1 p-3 text-inherit no-underline"
          data-stagger
        >
          <v-icon :icon="tile.icon" :color="tile.color" size="26" />
          <strong class="text-[28px] leading-none"><AnimatedNumber :value="tile.value" /></strong>
          <span class="text-muted text-sm leading-tight">{{ tile.title }}</span>
        </router-link>
      </section>

      <v-btn
        to="/issues/new"
        block
        size="x-large"
        color="primary"
        class="mt-4"
        prepend-icon="mdi-bullhorn-outline"
        data-stagger
      >
        Сообщить о проблеме
      </v-btn>

      <template v-if="hotIssue">
        <h2 class="section-title">Нужны голоса</h2>
        <div data-stagger>
          <IssueCard :issue="hotIssue" />
        </div>
      </template>

      <template v-if="nextEvent">
        <h2 class="section-title">Ближайшее событие</h2>
        <div data-stagger>
          <EventCard :event="nextEvent" />
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.hero {
  padding: 16px 16px 14px;
  background:
    radial-gradient(120% 90% at 0% 100%, rgba(var(--v-theme-primary), 0.12), transparent 60%),
    rgb(var(--v-theme-surface));
}
.bubble {
  position: relative;
  flex: 1;
  margin-bottom: 44px;
  padding: 12px 14px;
  border-radius: 18px 18px 18px 6px;
  background: rgba(var(--v-theme-primary), 0.1);
  font-size: 16px;
  font-weight: 500;
  line-height: 1.35;
}
.bubble::before {
  content: '';
  position: absolute;
  left: -8px;
  bottom: 8px;
  border: 8px solid transparent;
  border-right-color: rgba(var(--v-theme-primary), 0.1);
  border-left: 0;
}
</style>
