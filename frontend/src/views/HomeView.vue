<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { issuesApi } from '@/api/endpoints'
import type { IssueOut } from '@/api/types'
import AnnouncementCard from '@/components/announcements/AnnouncementCard.vue'
import AnimatedNumber from '@/components/common/AnimatedNumber.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import HealthRing from '@/components/common/HealthRing.vue'
import EventCard from '@/components/events/EventCard.vue'
import IssueCard from '@/components/issues/IssueCard.vue'
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import { Skeleton } from '@/components/ui/skeleton'
import { pageEnter, pageLeave, staggerIn } from '@/composables/useMotion'
import { hasNumericId, onRealtime } from '@/realtime/sse'
import { useAnnouncementsStore } from '@/stores/announcements'
import { useEventsStore } from '@/stores/events'
import { usePulseStore } from '@/stores/pulse'
import { useSessionStore } from '@/stores/session'
import { plural } from '@/utils/format'
import { MOOD_TITLES } from '@/utils/labels'

const session = useSessionStore()
const pulseStore = usePulseStore()
const events = useEventsStore()
const announcements = useAnnouncementsStore()
/** На главной одно объявление: закреплённое или самое свежее. */
const topAnnouncement = computed(() => announcements.items[0] ?? null)

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

const overdue = computed(() => pulse.value?.stats.overdue_issues ?? 0)

const alertActive = computed(() => !!pulse.value?.stats.active_alert)
/** Куда ведёт фраза Кузи: к тому, о чём он говорит. */
const phraseLink = computed(() => {
  const stats = pulse.value?.stats
  if (!stats) return null
  // просрочку показывает отдельная строка под кнопкой, здесь только тревога
  if (stats.active_alert) return { to: '/more/safety', label: 'Где укрыться' }
  return null
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
  if (!announcements.loaded) void announcements.load()
  void loadVoting()
})

watch(
  () => [pulse.value, hotIssue.value, nextEvent.value, topAnnouncement.value],
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
      <!-- Дом только что подключили из чата: без адреса не найти укрытия, без УК некуда слать обращения -->
      <router-link
        v-if="session.needsSetup"
        to="/more/house/edit"
        class="setup card-soft tap-card mb-3 flex items-center gap-3 p-4 no-underline"
        data-stagger
      >
        <v-icon icon="mdi-home-edit-outline" size="32" aria-hidden="true" />
        <span class="min-w-0 flex-1">
          <span class="block text-base font-bold">Настройте дом</span>
          <span class="block text-sm">
            Укажите адрес и управляющую компанию: так Кузя найдёт укрытия и отправит обращения
          </span>
        </span>
        <v-icon icon="mdi-chevron-right" aria-hidden="true" />
      </router-link>

      <!-- Кузя и его фраза -->
      <section class="hero card-soft" data-stagger>
        <div class="flex items-end gap-2">
          <KuzyaMascot :mood="pulse?.mood ?? 'ok'" :size="104" class="shrink-0" />
          <div class="bubble" aria-live="polite">
            <Transition :css="false" mode="out-in" @enter="pageEnter" @leave="pageLeave">
              <p :key="phraseKey" class="m-0">
                <template v-if="pulse">{{ pulse.phrase }}</template>
                <template v-else>Сейчас посмотрю, как дела у дома...</template>
              </p>
            </Transition>
            <router-link v-if="phraseLink" :to="phraseLink.to" class="bubble__link">
              {{ phraseLink.label }} <v-icon icon="mdi-chevron-right" size="20" />
            </router-link>
          </div>
        </div>
      </section>

      <!-- Главное действие: при тревоге - укрытие, иначе - сообщить о проблеме -->
      <v-btn
        v-if="alertActive"
        to="/more/safety"
        block
        size="x-large"
        color="deep"
        class="mt-3"
        prepend-icon="mdi-shield-home-outline"
        data-stagger
      >
        Идти в укрытие
      </v-btn>
      <v-btn
        v-else
        to="/issues/new"
        block
        size="x-large"
        color="primary"
        class="mt-3"
        prepend-icon="mdi-bullhorn-outline"
        data-stagger
      >
        Сообщить о проблеме
      </v-btn>
      <!-- Кузя и поиск в один тап с главной -->
      <div class="quick mt-3" data-stagger>
        <router-link to="/more/assistant" class="quick__item tap-card card-soft">
          <v-icon icon="mdi-chat-processing-outline" color="primary" size="24" aria-hidden="true" />
          <span>Спросить Кузю</span>
        </router-link>
        <router-link to="/more/search" class="quick__item tap-card card-soft">
          <v-icon icon="mdi-magnify" color="primary" size="24" aria-hidden="true" />
          <span>Поиск</span>
        </router-link>
      </div>

      <!-- Срочное: просроченные заявки. Одна строка с выходом к жалобе, а не красная плитка среди цифр -->
      <router-link
        v-if="overdue > 0"
        to="/issues?overdue=1"
        class="overdue-row tap-card mt-3"
        data-stagger
      >
        <v-icon icon="mdi-clock-alert-outline" size="28" aria-hidden="true" />
        <span class="min-w-0 flex-1">
          <span class="block font-bold">
            {{ overdue }}
            {{ plural(overdue, ['заявка просрочена', 'заявки просрочены', 'заявок просрочено']) }}
          </span>
          <span class="block text-sm opacity-90">Откройте и перешлите готовую жалобу</span>
        </span>
        <v-icon icon="mdi-chevron-right" aria-hidden="true" />
      </router-link>

      <!-- Что можно сделать прямо сейчас: поддержать заявку, записаться на событие -->
      <template v-if="hotIssue">
        <h2 class="section-title">Нужны голоса</h2>
        <div data-stagger>
          <IssueCard :issue="hotIssue" />
        </div>
      </template>

      <template v-if="nextEvent">
        <div class="section-head">
          <h2 class="section-title">Ближайшее событие</h2>
          <router-link to="/events" class="section-more">
            Все <v-icon icon="mdi-chevron-right" size="20" />
          </router-link>
        </div>
        <div data-stagger>
          <EventCard :event="nextEvent" />
        </div>
      </template>

      <template v-if="topAnnouncement">
        <div class="section-head">
          <h2 class="section-title">Объявления</h2>
          <router-link to="/announcements" class="section-more">
            Все<template v-if="announcements.items.length > 1">
              ({{ announcements.items.length }})</template
            >
            <v-icon icon="mdi-chevron-right" size="20" />
          </router-link>
        </div>
        <div data-stagger>
          <AnnouncementCard :item="topAnnouncement" clamp />
        </div>
      </template>

      <!-- Игровая часть: полезна, но не мешает главному -->
      <h2 class="section-title">Дом и вы</h2>
      <section
        class="card-soft flex items-center gap-4 p-4"
        data-stagger
        aria-label="Здоровье дома"
      >
        <HealthRing v-if="pulse" :score="pulse.score" :size="96" />
        <Skeleton v-else class="h-[96px] w-[96px] rounded-full" />
        <div class="min-w-0 flex-1">
          <h3 class="m-0 text-lg font-bold">Здоровье дома</h3>
          <div class="text-muted text-sm">{{ pulse ? MOOD_TITLES[pulse.mood] : 'Считаем...' }}</div>
          <div class="mt-3 text-sm font-semibold">Уровень дома: {{ pulse?.level ?? '...' }}</div>
          <v-progress-linear
            :model-value="xpPercent"
            color="primary"
            height="10"
            class="mt-1"
            aria-label="Прогресс уровня дома"
          />
          <div class="text-muted mt-1 text-sm tabular-nums">
            {{ pulse?.xp ?? 0 }} из {{ pulse?.xp_next ?? 0 }} очков
          </div>
        </div>
      </section>

      <router-link
        v-if="user"
        to="/more/achievements"
        class="card-soft tap-card mt-3 flex items-center gap-3 p-3 text-inherit no-underline"
        data-stagger
        aria-label="Мой уровень и награды"
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
            aria-label="Прогресс вашего уровня"
          />
          <div class="text-muted text-sm">
            <AnimatedNumber :value="user.points" />
            {{ plural(user.points, ['очко', 'очка', 'очков']) }}
            <template v-if="user.next_level_points">
              · ещё {{ user.next_level_points - user.points }} до уровня {{ user.level + 1 }}
            </template>
          </div>
        </div>
        <v-icon icon="mdi-chevron-right" />
      </router-link>
    </template>
  </div>
</template>

<style scoped>
.quick {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.quick__item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 6px;
  min-height: 76px;
  padding: 12px 16px;
  border-radius: var(--r-lg);
  color: inherit;
  font-weight: 600;
  text-decoration: none;
}

.setup {
  color: rgb(var(--v-theme-on-primary));
  background: rgb(var(--v-theme-primary));
  border-color: transparent;
}
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.section-more {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  font-weight: 700;
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}
.hero {
  padding: 16px 16px 14px;
  background:
    radial-gradient(120% 90% at 0% 100%, rgba(var(--v-theme-primary), 0.12), transparent 60%),
    rgb(var(--v-theme-surface));
}
.bubble {
  position: relative;
  flex: 1;
  margin-bottom: 36px;
  padding: 12px 14px;
  border-radius: 22px 22px 22px 6px;
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
/* Просрочка по DESIGN.md: заливка тревожного цвета, светлый текст, видно в обеих темах */
.overdue-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 64px;
  padding: 12px 14px 12px 16px;
  border-radius: var(--r-lg);
  color: rgb(var(--v-theme-on-deep));
  background: rgb(var(--v-theme-deep));
  text-decoration: none;
}
.bubble__link {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  margin-bottom: -10px;
  font-weight: 700;
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}
</style>
