<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { errorMessage } from '@/api/client'
import { achievementsApi } from '@/api/endpoints'
import type { AchievementOut, AchievementsOut } from '@/api/types'
import AnimatedNumber from '@/components/common/AnimatedNumber.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import { Skeleton } from '@/components/ui/skeleton'
import { useStagger } from '@/composables/useMotion'
import { onRealtime } from '@/realtime/sse'
import { useSessionStore } from '@/stores/session'
import { formatDate, fullName } from '@/utils/format'

const session = useSessionStore()
const data = ref<AchievementsOut | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const selected = ref<AchievementOut | null>(null)
const grid = ref<HTMLElement | null>(null)

const earned = computed(() => data.value?.items.filter((a) => a.earned).length ?? 0)
const total = computed(() => data.value?.items.length ?? 0)
const user = computed(() => session.me?.user)
const levelProgress = computed(() => {
  const u = user.value
  if (!u?.next_level_points) return 100
  return Math.min(100, (u.points / u.next_level_points) * 100)
})
const sorted = computed(() =>
  [...(data.value?.items ?? [])].sort((a, b) => Number(b.earned) - Number(a.earned)),
)

useStagger(grid, () => sorted.value.length)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    data.value = await achievementsApi.list()
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
const off = onRealtime('achievement.awarded', () => void load())
onBeforeUnmount(off)

function isMe(row: { is_me?: boolean; user: { id: number } }): boolean {
  return row.is_me ?? row.user.id === user.value?.id
}
const MEDALS = ['#00B4D8', '#90E0EF', '#0077B6']
</script>

<template>
  <div class="page">
    <section v-if="user" class="card-soft p-4">
      <div class="flex items-center gap-3">
        <v-avatar color="primary" size="56"
          ><span class="text-2xl font-bold">{{ user.level }}</span></v-avatar
        >
        <div class="flex-1">
          <div class="text-muted text-sm">Ваш уровень</div>
          <div class="text-lg font-bold">{{ user.level_title }}</div>
        </div>
        <div class="text-right">
          <div class="text-2xl font-extrabold text-primary">
            <AnimatedNumber :value="user.points" />
          </div>
          <div class="text-muted text-sm">очков</div>
        </div>
      </div>
      <v-progress-linear
        :model-value="levelProgress"
        color="primary"
        height="10"
        class="mt-3"
        aria-label="Прогресс до следующего уровня"
      />
      <div v-if="user.next_level_points" class="text-muted mt-1 text-sm">
        До следующего уровня: {{ Math.max(0, user.next_level_points - user.points) }} очков
      </div>
    </section>

    <div v-if="loading && !data" class="mt-4 grid grid-cols-3 gap-3" aria-busy="true">
      <Skeleton v-for="i in 9" :key="i" class="h-[112px] rounded-2xl" />
    </div>
    <ErrorState v-else-if="error && !data" :message="error" :retrying="loading" @retry="load" />

    <template v-else-if="data">
      <div class="mt-5 flex items-baseline justify-between">
        <h2 class="section-title !my-0">Награды</h2>
        <span class="text-muted text-sm">{{ earned }} из {{ total }}</span>
      </div>
      <v-progress-linear
        :model-value="total ? (earned / total) * 100 : 0"
        color="primary"
        height="6"
        class="mt-2 mb-3"
        aria-label="Сколько наград получено"
      />

      <div ref="grid" class="grid grid-cols-3 gap-3">
        <button
          v-for="a in sorted"
          :key="a.code"
          type="button"
          class="badge tap-card"
          :class="{ 'badge--locked': !a.earned }"
          data-stagger
          :aria-label="`${a.title}. ${a.earned ? 'Получено' : 'Ещё не получено'}`"
          @click="selected = a"
        >
          <span class="badge__icon">
            <v-icon :icon="a.earned ? a.icon : 'mdi-lock-outline'" size="30" />
          </span>
          <span class="badge__title">{{ a.title }}</span>
          <span class="text-muted text-sm">+{{ a.points }}</span>
        </button>
      </div>

      <h2 class="section-title">Рейтинг соседей</h2>
      <ol class="card-soft m-0 list-none p-0">
        <li
          v-for="row in data.leaderboard"
          :key="row.user.id"
          class="leader"
          :class="{ 'leader--me': isMe(row) }"
        >
          <span class="leader__rank">
            <v-icon v-if="row.rank <= 3" icon="mdi-medal" :color="MEDALS[row.rank - 1]" size="26" />
            <template v-else>{{ row.rank }}</template>
          </span>
          <UserAvatar :user="row.user" :size="36" />
          <div class="min-w-0 flex-1">
            <router-link
              :to="`/people/${row.user.id}`"
              class="block truncate font-semibold text-inherit no-underline"
            >
              {{ fullName(row.user) }}<span v-if="isMe(row)" class="text-primary"> (вы)</span>
            </router-link>
            <div class="text-muted text-sm">{{ row.level_title }}</div>
          </div>
          <strong class="tabular-nums">{{ row.points }}</strong>
        </li>
      </ol>
    </template>

    <v-dialog :model-value="!!selected" max-width="360" @update:model-value="selected = null">
      <v-card v-if="selected" rounded="xl" class="p-2 text-center">
        <v-card-text>
          <v-avatar :color="selected.earned ? 'warning' : 'surface-variant'" size="72">
            <v-icon :icon="selected.earned ? selected.icon : 'mdi-lock-outline'" size="40" />
          </v-avatar>
          <h3 class="mt-3 mb-1 text-lg font-bold">{{ selected.title }}</h3>
          <p class="m-0">{{ selected.description }}</p>
          <p class="text-muted mt-2 mb-0 text-sm">
            <template v-if="selected.earned && selected.awarded_at"
              >Получено {{ formatDate(selected.awarded_at) }}</template
            >
            <template v-else-if="!selected.earned"
              >Ещё не получено · +{{ selected.points }} очков</template
            >
          </p>
        </v-card-text>
        <v-card-actions>
          <v-btn block variant="tonal" color="primary" @click="selected = null">Понятно</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 6px 10px;
  border-radius: 18px;
  border: 1px solid rgba(var(--v-border-color), 0.1);
  background: rgb(var(--v-theme-surface));
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.badge__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  color: rgb(var(--v-theme-on-primary));
  background: linear-gradient(135deg, rgb(var(--v-theme-tertiary)), rgb(var(--v-theme-primary)));
  box-shadow: 0 6px 14px -6px rgba(var(--v-theme-primary), 0.8);
}
.badge__title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.2;
  text-align: center;
}
.badge--locked .badge__icon {
  color: rgba(var(--v-theme-on-surface), 0.45);
  background: rgba(var(--v-theme-on-surface), 0.08);
  box-shadow: none;
}
.badge--locked .badge__title {
  color: rgba(var(--v-theme-on-surface), 0.72);
}
.leader {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.08);
}
.leader:last-child {
  border-bottom: 0;
}
.leader--me {
  background: rgba(var(--v-theme-primary), 0.08);
}
.leader__rank {
  width: 28px;
  text-align: center;
  font-weight: 700;
}
</style>
