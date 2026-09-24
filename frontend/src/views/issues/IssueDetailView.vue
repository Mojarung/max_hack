<script setup lang="ts">
import { computed, onMounted, ref, toRef, defineAsyncComponent } from 'vue'
import { ApiError, errorMessage } from '@/api/client'
import ErrorState from '@/components/common/ErrorState.vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import IssueStatusControls from '@/components/issues/IssueStatusControls.vue'
import StatusChip from '@/components/issues/StatusChip.vue'
import VoteProgress from '@/components/issues/VoteProgress.vue'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import { Skeleton } from '@/components/ui/skeleton'
import { useCountdown } from '@/composables/useCountdown'
import { confetti, pop } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { copyText, haptic, shareContent } from '@/max/bridge'
import { issueDeepLink } from '@/max/deeplink'
import { useIssuesStore } from '@/stores/issues'
import { useSessionStore } from '@/stores/session'
import { formatDateTime, formatHours, formatRelative, fullName, pluralize } from '@/utils/format'
import { ISSUE_STATUS_META, ISSUE_STATUS_TITLES, issueCategoryIcon } from '@/utils/labels'

const PhotoGallery = defineAsyncComponent(() => import('@/components/common/PhotoGallery.vue'))

const props = defineProps<{ id: number }>()

const store = useIssuesStore()
const session = useSessionStore()
const loading = ref(false)
const error = ref<string | null>(null)
const notFound = ref(false)
const voting = ref(false)
const voteBlock = ref<HTMLElement | null>(null)
const complaintOpen = ref(false)

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
const overdue = computed(
  () => !!issue.value?.is_overdue || (slaActive.value && !!countdown.value?.overdue),
)

/**
 * Жалоба в Госжилинспекцию при просрочке. Собирается из данных заявки: житель
 * пересылает её в чат или копирует, а Кузя параллельно сообщает о просрочке в домовой чат.
 */
const complaintText = computed(() => {
  const i = issue.value
  if (!i) return ''
  const address = session.me?.house.address ?? ''
  const lines = [
    'В Государственную жилищную инспекцию',
    address ? `от жителей дома по адресу: ${address}` : 'от жителей дома',
    '',
    'ЖАЛОБА',
    '',
    `${i.sent_at ? formatDateTime(i.sent_at) : 'Ранее'} жители направили в ${orgName.value} обращение: «${i.title}».`,
    i.description,
    '',
    i.deadline_hours
      ? `Нормативный срок устранения (${formatHours(i.deadline_hours)}) истёк${i.deadline_at ? ` ${formatDateTime(i.deadline_at)}` : ''}, неисправность не устранена.`
      : 'Срок устранения истёк, неисправность не устранена.',
    i.legal_basis ? `Основание: ${i.legal_basis}.` : '',
    `Обращение поддержали ${pluralize(i.votes_count, ['житель', 'жителя', 'жителей'])}.`,
    '',
    `Просим провести проверку и обязать ${orgName.value} устранить нарушение.`,
  ]
  return lines.filter((line, idx, all) => line !== '' || all[idx - 1] !== '').join('\n')
})
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

/** Позвать соседей: сообщение со ссылкой, которая откроет эту заявку в мини-приложении. */
async function invite(): Promise<void> {
  if (!issue.value) return
  const link = issueDeepLink(issue.value.id, session.me?.bot_username)
  const text = `Соседи, поддержите заявку «${issue.value.title}»: нужно ещё ${pluralize(remaining.value, ['голос', 'голоса', 'голосов'])}, и Кузя отправит обращение.`
  const result = await shareContent(text, link ?? undefined)
  if (result === 'copied') notify.success('Приглашение скопировано', 'Вставьте его в чат дома')
  else if (result === 'failed') notify.error(new Error('Не получилось поделиться'))
}

async function copy(text: string | null | undefined): Promise<void> {
  if (!text) return
  const ok = await copyText(text)
  if (ok) notify.success('Текст скопирован')
  else notify.error(new Error('Не удалось скопировать текст'))
}

async function share(text: string | null | undefined): Promise<void> {
  if (!text) return
  const result = await shareContent(text)
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
      <PhotoGallery :photos="issue.photos" :alt="issue.title" :height="180" />
      <div
        v-if="!issue.photos.length"
        class="flex h-[96px] items-center justify-center rounded-2xl bg-surface-variant"
      >
        <v-icon :icon="issueCategoryIcon(issue.category)" size="48" color="primary" />
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-2">
        <StatusChip :status="issue.status" :overdue="overdue" />
        <v-chip variant="outlined" :prepend-icon="issueCategoryIcon(issue.category)">
          {{ issue.category_title }}
        </v-chip>
      </div>
      <h2 class="mt-2 mb-1 text-[22px] leading-tight font-bold">{{ issue.title }}</h2>
      <div class="text-muted flex items-center gap-2 text-sm">
        <UserAvatar :user="issue.author" :size="28" />
        <span>{{ fullName(issue.author) }} · {{ formatRelative(issue.created_at) }}</span>
      </div>
      <p v-if="issue.location_hint" class="mt-2 mb-0 flex items-center gap-1 font-semibold">
        <v-icon icon="mdi-map-marker-outline" size="20" color="primary" />
        {{ issue.location_hint }}
      </p>

      <!-- Голосование: главное действие экрана, поэтому сразу под заголовком -->
      <section
        v-if="issue.status === 'voting'"
        ref="voteBlock"
        class="card-soft relative mt-4 overflow-hidden p-4"
        aria-label="Голосование"
      >
        <VoteProgress :count="issue.votes_count" :needed="issue.votes_needed" />
        <p class="mt-3 mb-4">
          <template v-if="remaining > 0">
            <strong>Пока не чинят:</strong> обращение ещё не отправлено. Когда поддержат ещё
            <strong>{{ pluralize(remaining, ['сосед', 'соседа', 'соседей']) }}</strong
            >, Кузя отправит его в {{ orgName }}.
          </template>
          <template v-else>Голосов хватает, Кузя готовит обращение в {{ orgName }}.</template>
        </p>
        <template v-if="issue.voted_by_me">
          <div class="voted" role="status">
            <v-icon icon="mdi-check-circle" size="26" />
            <span>Вы поддержали. Кузя учтёт ваш голос в обращении.</span>
          </div>
          <v-btn
            block
            size="large"
            color="primary"
            variant="tonal"
            class="mt-3"
            prepend-icon="mdi-account-multiple-plus-outline"
            @click="invite"
          >
            Позвать соседей
          </v-btn>
          <v-btn
            block
            variant="text"
            size="large"
            class="mt-1"
            :loading="voting"
            @click="toggleVote"
          >
            Отозвать голос
          </v-btn>
        </template>
        <v-btn
          v-else
          block
          size="x-large"
          color="primary"
          prepend-icon="mdi-hand-back-right-outline"
          :loading="voting"
          @click="toggleVote"
        >
          Меня это тоже касается
        </v-btn>
      </section>

      <!-- Просрочка: что случилось и что делать дальше -->
      <section v-if="overdue" class="overdue mt-4" aria-label="Срок вышел">
        <div class="flex items-center gap-3">
          <v-icon icon="mdi-clock-alert" size="32" />
          <div>
            <div class="text-xl leading-tight font-bold">Срок вышел</div>
            <div v-if="countdown">{{ countdown.text }}</div>
          </div>
        </div>
        <p class="mt-3 mb-4">
          Не починили вовремя. Кузя подготовил жалобу в Госжилинспекцию: она может обязать
          исполнителя всё исправить. Осталось переслать её.
        </p>
        <v-btn
          block
          size="x-large"
          color="light"
          class="overdue__cta"
          prepend-icon="mdi-file-document-alert-outline"
          @click="complaintOpen = true"
        >
          Посмотреть жалобу
        </v-btn>
      </section>

      <p class="pre-wrap mt-4 mb-0 text-base leading-relaxed">{{ issue.description }}</p>

      <!-- Кто отвечает и сроки -->
      <section v-if="issue.responsible_org" class="card-soft mt-4 p-4" aria-labelledby="who">
        <h3 id="who" class="m-0 text-base font-bold">Кто отвечает</h3>
        <div class="mt-1 text-lg leading-snug font-bold text-primary">
          {{ issue.responsible_org.name }}
        </div>
        <div class="text-muted text-sm">{{ issue.responsible_org.kind_title }}</div>

        <div v-if="issue.deadline_hours" class="mt-3">
          По закону должны устранить за <strong>{{ formatHours(issue.deadline_hours) }}</strong>
          <template v-if="issue.status === 'voting'"> после отправки обращения</template>.
        </div>
        <div
          v-if="slaActive && countdown && !overdue"
          class="sla mt-3"
          :class="{ 'sla--urgent': countdown.urgent }"
          role="timer"
        >
          <v-icon icon="mdi-timer-sand" size="26" />
          <div>
            <div class="text-sm">Осталось</div>
            <div class="text-xl font-bold">{{ countdown.text }}</div>
          </div>
        </div>
        <div v-if="slaActive && !overdue" class="text-muted mt-2 text-sm">
          Не успеют - Кузя подготовит жалобу в Госжилинспекцию и напишет в чат дома.
        </div>
        <div v-if="issue.sent_at" class="text-muted mt-2 text-sm">
          Обращение отправлено {{ formatDateTime(issue.sent_at) }}
        </div>
        <details v-if="issue.legal_basis" class="basis mt-3">
          <summary>
            <span class="flex-1">Почему такой срок</span>
            <v-icon icon="mdi-chevron-down" class="basis__chevron" />
          </summary>
          <p class="text-muted mt-2 mb-0 text-sm">
            {{ issue.legal_basis }}. Справочно: точный срок зависит от вида работ.
          </p>
        </details>
      </section>

      <!-- Текст обращения -->
      <v-expansion-panels v-if="issue.appeal_text" class="mt-4" variant="accordion">
        <v-expansion-panel rounded="xl" elevation="0" class="card-soft">
          <v-expansion-panel-title>
            <span class="flex items-center gap-2 font-semibold">
              <v-icon icon="mdi-file-document-outline" color="primary" /> Что отправил Кузя
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
                @click="copy(issue.appeal_text)"
              >
                Скопировать
              </v-btn>
              <v-btn
                class="flex-1"
                variant="tonal"
                color="primary"
                prepend-icon="mdi-share-variant"
                @click="share(issue.appeal_text)"
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
            :dot-color="ISSUE_STATUS_META[step.status]?.color ?? 'muted'"
            :icon="ISSUE_STATUS_META[step.status]?.icon"
            size="small"
          >
            <div class="font-semibold">
              {{ ISSUE_STATUS_TITLES[step.status] ?? step.status_title }}
            </div>
            <div class="text-muted text-sm">{{ formatDateTime(step.created_at) }}</div>
            <div v-if="step.note" class="mt-1 text-sm">{{ step.note }}</div>
          </v-timeline-item>
        </v-timeline>
      </section>

      <IssueStatusControls v-if="canManage" :issue="issue" class="mt-4" />

      <Drawer v-model:open="complaintOpen">
        <DrawerContent>
          <DrawerHeader
            title="Жалоба в Госжилинспекцию"
            description="Текст готов. Нажмите «Поделиться» и выберите чат дома или приложение Госуслуги (раздел жалоб на ЖКХ)."
          />
          <p class="complaint pre-wrap" tabindex="0" aria-label="Текст жалобы">
            {{ complaintText }}
          </p>
          <v-btn
            block
            size="x-large"
            color="primary"
            class="mt-3"
            prepend-icon="mdi-share-variant"
            @click="share(complaintText)"
          >
            Поделиться жалобой
          </v-btn>
          <v-btn
            block
            size="large"
            variant="text"
            class="mt-1"
            prepend-icon="mdi-content-copy"
            @click="copy(complaintText)"
          >
            Скопировать текст
          </v-btn>
        </DrawerContent>
      </Drawer>
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
  color: rgb(var(--v-theme-on-surface));
  background: rgba(var(--v-theme-primary), 0.1);
}
.sla--urgent {
  color: rgb(var(--v-theme-on-primary));
  background: rgb(var(--v-theme-primary));
}
/* Просрочка по DESIGN.md: самый тёмный цвет, заливной, светлый текст */
.overdue {
  padding: 16px;
  border-radius: var(--radius-card);
  color: rgb(var(--v-theme-on-deep));
  background: rgb(var(--v-theme-deep));
}
.overdue__cta {
  color: rgb(var(--v-theme-deep)) !important;
  background: rgb(var(--v-theme-on-deep)) !important;
  font-weight: 700;
}
.voted {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding: 10px 14px;
  border-radius: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.12);
}
.basis summary {
  min-height: 44px;
  list-style: none;
  display: flex;
  align-items: center;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
}
.basis summary::-webkit-details-marker {
  display: none;
}
.basis[open] .basis__chevron {
  transform: rotate(180deg);
}
.complaint {
  max-height: 40dvh;
  overflow-y: auto;
  margin: 0;
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 15px;
  line-height: 1.5;
  background: rgba(var(--v-theme-primary), 0.08);
}
</style>
