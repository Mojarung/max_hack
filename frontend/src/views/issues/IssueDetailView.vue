<script setup lang="ts">
import { computed, onMounted, ref, toRef } from 'vue'
import { ApiError, errorMessage } from '@/api/client'
import ErrorState from '@/components/common/ErrorState.vue'
import PhotoGallery from '@/components/common/PhotoGallery.vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import IssueStatusControls from '@/components/issues/IssueStatusControls.vue'
import StatusChip from '@/components/issues/StatusChip.vue'
import VoteProgress from '@/components/issues/VoteProgress.vue'
import { Skeleton } from '@/components/ui/skeleton'
import { useCountdown } from '@/composables/useCountdown'
import { confetti, pop } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { copyText, haptic, shareContent } from '@/max/bridge'
import { useIssuesStore } from '@/stores/issues'
import { useSessionStore } from '@/stores/session'
import { formatDateTime, formatRelative, fullName, plural } from '@/utils/format'
import { ISSUE_STATUS_META, issueCategoryIcon } from '@/utils/labels'

const props = defineProps<{ id: number }>()

const store = useIssuesStore()
const session = useSessionStore()
const loading = ref(false)
const error = ref<string | null>(null)
const notFound = ref(false)
const voting = ref(false)
const voteBlock = ref<HTMLElement | null>(null)

const issue = computed(() => store.details[props.id] ?? null)
const remaining = computed(() =>
  issue.value ? Math.max(0, issue.value.votes_needed - issue.value.votes_count) : 0,
)
const orgName = computed(
  () => issue.value?.responsible_org?.name ?? session.me?.house.uk_name ?? 'управляющую компанию',
)
const countdown = useCountdown(toRef(() => issue.value?.deadline_at))
const slaActive = computed(
  () => !!issue.value?.deadline_at && ['sent', 'in_progress'].includes(issue.value.status),
)
const canManage = computed(
  () =>
    !!issue.value &&
    (session.isAdmin || issue.value.author?.id === session.me?.user.id) &&
    issue.value.status !== 'resolved' &&
    issue.value.status !== 'rejected',
)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  notFound.value = false
  try {
    await store.fetchDetail(props.id)
  } catch (e) {
    notFound.value = e instanceof ApiError && e.status === 404
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function toggleVote(): Promise<void> {
  if (!issue.value || voting.value) return
  voting.value = true
  const wasVoted = issue.value.voted_by_me
  haptic.impact('medium')
  try {
    const updated = await store.toggleVote(props.id)
    if (wasVoted) {
      notify.info('Голос отозван')
    } else if (updated.status !== 'voting') {
      confetti(voteBlock.value)
      notify.success('Порог набран!', `Кузя отправил обращение в ${orgName.value}`)
    } else {
      pop(voteBlock.value)
      notify.success('Голос учтён, спасибо!')
    }
  } catch (e) {
    notify.error(e, 'Голос не сохранился')
  } finally {
    voting.value = false
  }
}

async function copyAppeal(): Promise<void> {
  if (!issue.value?.appeal_text) return
  const ok = await copyText(issue.value.appeal_text)
  if (ok) notify.success('Текст обращения скопирован')
  else notify.error(new Error('Не удалось скопировать текст'))
}

async function shareAppeal(): Promise<void> {
  if (!issue.value?.appeal_text) return
  const result = await shareContent(issue.value.appeal_text)
  if (result === 'copied') notify.success('Текст скопирован, его можно вставить в чат')
  else if (result === 'failed') notify.error(new Error('Не получилось поделиться'))
}
</script>

<template>
  <div class="page">
    <div v-if="loading && !issue" aria-busy="true" aria-label="Загрузка">
      <Skeleton class="h-[220px] w-full rounded-2xl" />
      <Skeleton class="mt-4 h-6 w-4/5" />
      <Skeleton class="mt-2 h-4 w-1/2" />
      <Skeleton class="mt-6 h-[120px] w-full rounded-2xl" />
    </div>

    <ErrorState
      v-else-if="error && !issue"
      :title="notFound ? 'Проблема не найдена' : 'Не получилось загрузить'"
      :message="error"
      :retrying="loading"
      @retry="load"
    />

    <article v-else-if="issue">
      <PhotoGallery :photos="issue.photos" :alt="issue.title" />
      <div
        v-if="!issue.photos.length"
        class="flex h-[120px] items-center justify-center rounded-2xl bg-surface-variant"
      >
        <v-icon :icon="issueCategoryIcon(issue.category)" size="56" color="primary" />
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-2">
        <StatusChip
          :status="issue.status"
          :title="issue.status_title"
          :overdue="issue.is_overdue"
        />
        <v-chip size="small" variant="outlined" :prepend-icon="issueCategoryIcon(issue.category)">
          {{ issue.category_title }}
        </v-chip>
      </div>
      <h2 class="mt-2 mb-1 text-[22px] leading-tight font-bold">{{ issue.title }}</h2>
      <div class="text-muted flex items-center gap-2 text-sm">
        <UserAvatar :user="issue.author" :size="24" />
        <span>{{ fullName(issue.author) }} · {{ formatRelative(issue.created_at) }}</span>
      </div>
      <p v-if="issue.location_hint" class="mt-2 mb-0 flex items-center gap-1 text-sm">
        <v-icon icon="mdi-map-marker-outline" size="18" color="primary" /> {{ issue.location_hint }}
      </p>
      <p class="pre-wrap mt-3 mb-0 text-base leading-relaxed">{{ issue.description }}</p>

      <!-- Голосование -->
      <section
        v-if="issue.status === 'voting'"
        ref="voteBlock"
        class="card-soft relative mt-4 overflow-hidden p-4"
        aria-label="Голосование"
      >
        <h3 class="m-0 mb-3 text-lg font-bold">Поддержите обращение</h3>
        <VoteProgress :count="issue.votes_count" :needed="issue.votes_needed" />
        <p class="mt-3 mb-3 text-[15px]">
          <template v-if="remaining > 0">
            Ещё
            <strong>{{ remaining }} {{ plural(remaining, ['голос', 'голоса', 'голосов']) }}</strong>
            и Кузя отправит обращение в {{ orgName }}.
          </template>
          <template v-else>Порог набран, Кузя готовит обращение в {{ orgName }}.</template>
        </p>
        <v-btn
          block
          size="x-large"
          :color="issue.voted_by_me ? 'success' : 'primary'"
          :variant="issue.voted_by_me ? 'tonal' : 'flat'"
          :prepend-icon="issue.voted_by_me ? 'mdi-check-circle' : 'mdi-hand-back-right-outline'"
          :loading="voting"
          :aria-pressed="issue.voted_by_me"
          @click="toggleVote"
        >
          {{ issue.voted_by_me ? 'Вы поддержали' : 'Меня это тоже касается' }}
        </v-btn>
        <v-btn
          v-if="issue.voted_by_me"
          block
          variant="text"
          class="mt-1"
          :disabled="voting"
          @click="toggleVote"
        >
          Отозвать голос
        </v-btn>
      </section>

      <!-- Кто отвечает и сроки -->
      <section v-if="issue.responsible_org" class="card-soft mt-4 p-4" aria-label="Кто отвечает">
        <div class="text-muted text-sm">{{ issue.responsible_org.kind_title }}</div>
        <div class="text-lg font-bold">{{ issue.responsible_org.name }}</div>
        <div v-if="issue.legal_basis" class="text-muted mt-2 flex items-start gap-1.5 text-sm">
          <v-icon icon="mdi-scale-balance" size="18" class="mt-px" />
          <span>{{ issue.legal_basis }}</span>
        </div>
        <div v-if="issue.deadline_hours" class="mt-2 text-sm">
          Срок устранения по нормативу: <strong>{{ issue.deadline_hours }} ч</strong>
        </div>
        <div
          v-if="slaActive && countdown"
          class="sla mt-3"
          :class="{
            'sla--overdue': countdown.overdue || issue.is_overdue,
            'sla--urgent': countdown.urgent,
          }"
          role="timer"
        >
          <v-icon :icon="countdown.overdue ? 'mdi-clock-alert' : 'mdi-timer-sand'" size="26" />
          <div>
            <div class="text-sm opacity-80">
              {{ countdown.overdue ? 'Срок вышел' : 'До конца срока' }}
            </div>
            <div class="text-xl font-bold">{{ countdown.text }}</div>
          </div>
        </div>
        <div v-if="issue.sent_at" class="text-muted mt-2 text-sm">
          Обращение отправлено {{ formatDateTime(issue.sent_at) }}
        </div>
      </section>

      <!-- Текст обращения -->
      <v-expansion-panels v-if="issue.appeal_text" class="mt-4" variant="accordion">
        <v-expansion-panel rounded="xl" elevation="0" class="card-soft">
          <v-expansion-panel-title>
            <span class="flex items-center gap-2 font-semibold">
              <v-icon icon="mdi-file-document-outline" color="primary" /> Текст обращения
            </span>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <p class="pre-wrap mt-0 text-[15px] leading-relaxed">{{ issue.appeal_text }}</p>
            <div class="flex gap-2">
              <v-btn
                class="flex-1"
                variant="tonal"
                color="primary"
                prepend-icon="mdi-content-copy"
                @click="copyAppeal"
              >
                Скопировать
              </v-btn>
              <v-btn
                class="flex-1"
                variant="tonal"
                color="secondary"
                prepend-icon="mdi-share-variant"
                @click="shareAppeal"
              >
                Поделиться
              </v-btn>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <!-- История -->
      <section v-if="issue.timeline.length" class="mt-4" aria-label="История">
        <h3 class="section-title !mt-2">Как идут дела</h3>
        <v-timeline side="end" density="compact" align="start" truncate-line="both">
          <v-timeline-item
            v-for="(step, i) in issue.timeline"
            :key="`${step.status}-${step.created_at}-${i}`"
            :dot-color="ISSUE_STATUS_META[step.status]?.color ?? 'grey'"
            :icon="ISSUE_STATUS_META[step.status]?.icon"
            size="small"
          >
            <div class="font-semibold">{{ step.status_title }}</div>
            <div class="text-muted text-sm">{{ formatDateTime(step.created_at) }}</div>
            <div v-if="step.note" class="mt-1 text-sm">{{ step.note }}</div>
          </v-timeline-item>
        </v-timeline>
      </section>

      <IssueStatusControls v-if="canManage" :issue="issue" class="mt-4" />
    </article>
  </div>
</template>

<style scoped>
.sla {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  color: rgb(var(--v-theme-secondary));
  background: rgba(var(--v-theme-secondary), 0.1);
}
.sla--urgent {
  color: rgb(var(--v-theme-warning));
  background: rgba(var(--v-theme-warning), 0.12);
}
.sla--overdue {
  color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.12);
}
</style>
