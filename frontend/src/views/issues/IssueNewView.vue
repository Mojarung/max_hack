<script setup lang="ts">
import { watchDebounced } from '@vueuse/core'
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { issuesApi } from '@/api/endpoints'
import type { Classification, IssueDetail, IssueOut } from '@/api/types'
import PhotoPicker from '@/components/common/PhotoPicker.vue'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import { useDirtyGuard } from '@/composables/useDirtyGuard'
import { confetti, pageEnter } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { haptic } from '@/max/bridge'
import { useIssuesStore } from '@/stores/issues'
import { formatHours, orgRecipient, orgTitle, plural } from '@/utils/format'
import { ISSUE_STATUS_TITLES } from '@/utils/labels'

const MIN_TEXT = 10
const router = useRouter()
const store = useIssuesStore()

const step = ref<1 | 2>(1)
const description = ref('')
const title = ref('')
const locationHint = ref('')
const photos = ref<File[]>([])

const classification = ref<Classification | null>(null)
const classifying = ref(false)
const similar = ref<IssueOut[]>([])
const supporting = ref<number | null>(null)

const submitting = ref(false)
const progress = ref(0)
const created = ref<IssueDetail | null>(null)
const successBox = ref<HTMLElement | null>(null)

const textOk = computed(() => description.value.trim().length >= MIN_TEXT)
const dirty = computed(
  () => !created.value && (description.value.trim().length > 0 || photos.value.length > 0),
)
useDirtyGuard(dirty)

/** Похожие заявки ищем отдельно от классификации: поиск быстрый, классификация ждёт ИИ. */
const similarFor = ref('')
const advancing = ref(false)
const similarOpen = ref(false)
let similarController: AbortController | null = null
let classifyController: AbortController | null = null
const SIMILAR_WAIT_MS = 3000

function openSimilar(list: IssueOut[]): IssueOut[] {
  return list
    .filter((i) => i.status === 'voting' || i.status === 'sent' || i.status === 'in_progress')
    .slice(0, 3)
}

let pendingSimilar: { text: string; promise: Promise<void> } | null = null

/** Один запрос на один текст: «Дальше» и поиск при вводе ждут один и тот же ответ, а не отменяют друг друга. */
function findSimilar(text: string): Promise<void> {
  if (similarFor.value === text) return Promise.resolve()
  if (pendingSimilar?.text === text) return pendingSimilar.promise
  similarController?.abort()
  const controller = new AbortController()
  similarController = controller
  const promise = (async () => {
    try {
      const found = await issuesApi.similar(text, controller.signal)
      if (controller.signal.aborted) return
      similar.value = openSimilar(found)
      similarFor.value = text
    } catch {
      if (!controller.signal.aborted) similarFor.value = text
    } finally {
      if (similarController === controller) pendingSimilar = null
    }
  })()
  pendingSimilar = { text, promise }
  return promise
}

watchDebounced(
  description,
  async (text) => {
    classifyController?.abort()
    const trimmed = text.trim()
    if (trimmed.length < 8) {
      classification.value = null
      similar.value = []
      similarFor.value = ''
      return
    }
    void findSimilar(trimmed)
    const controller = new AbortController()
    classifyController = controller
    classifying.value = true
    try {
      const cls = await issuesApi.classify(trimmed, controller.signal)
      if (!controller.signal.aborted) classification.value = cls
    } catch {
      // без подсказки Кузи форма всё равно работает
    } finally {
      if (classifyController === controller) classifying.value = false
    }
  },
  { debounce: 600 },
)

async function support(issue: IssueOut): Promise<void> {
  if (issue.voted_by_me) {
    await router.push(`/issues/${issue.id}`)
    return
  }
  supporting.value = issue.id
  haptic.impact('medium')
  try {
    const detail = await issuesApi.vote(issue.id)
    store.storeDetail(detail)
    description.value = ''
    photos.value = []
    notify.success('Голос учтён')
    await router.replace(`/issues/${issue.id}`)
  } catch (e) {
    notify.error(e, 'Не удалось проголосовать')
  } finally {
    supporting.value = null
  }
}

/**
 * «Дальше»: сначала убеждаемся, что такой заявки ещё нет. Иначе житель, нажавший быстро,
 * создал бы дубль вместо того, чтобы поддержать соседа.
 */
async function next(): Promise<void> {
  if (!textOk.value || advancing.value) return
  haptic.impact('light')
  // загрузка на кнопке сразу: без неё житель решит, что не сработало, и нажмёт ещё раз
  advancing.value = true
  const text = description.value.trim()
  try {
    if (similarFor.value !== text) {
      await Promise.race([findSimilar(text), new Promise((r) => setTimeout(r, SIMILAR_WAIT_MS))])
    }
  } finally {
    advancing.value = false
  }
  if (similar.value.length && similarFor.value === text) {
    similarOpen.value = true
    return
  }
  goStep2()
}

function goStep2(): void {
  similarOpen.value = false
  step.value = 2
  window.scrollTo({ top: 0 })
}

async function submit(): Promise<void> {
  if (!textOk.value || submitting.value) return
  submitting.value = true
  progress.value = 0
  const form = new FormData()
  form.append('description', description.value.trim())
  if (title.value.trim()) form.append('title', title.value.trim())
  if (locationHint.value.trim()) form.append('location_hint', locationHint.value.trim())
  photos.value.forEach((file) => form.append('photos', file, file.name))
  try {
    const issue = await issuesApi.create(
      form,
      (fraction) => (progress.value = Math.round(fraction * 100)),
    )
    store.storeDetail(issue)
    created.value = issue
    haptic.notify('success')
    await nextTick()
    if (successBox.value) pageEnter(successBox.value, () => undefined)
    setTimeout(() => confetti(successBox.value, 60), 150)
  } catch (e) {
    notify.error(e, 'Не удалось отправить')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <!-- Успех -->
    <section
      v-if="created"
      ref="successBox"
      class="card-soft relative flex flex-col items-center overflow-hidden px-4 py-8 text-center"
      role="status"
    >
      <KuzyaMascot mood="proud" :size="150" />
      <h2 class="mt-4 mb-2 text-2xl font-bold">Спасибо! Кузя всё записал</h2>
      <p class="text-muted m-0 max-w-[340px]">
        <template v-if="created.status === 'voting'">
          Соседи увидят заявку и смогут её поддержать. Нужно
          {{ created.votes_needed }}
          {{ plural(created.votes_needed, ['голос', 'голоса', 'голосов']) }}, и обращение уйдёт
          {{ orgRecipient(created.responsible_org?.name) || 'в управляющую компанию' }}.
        </template>
        <template v-else>Кузя уже отправил обращение тем, кто отвечает за ремонт.</template>
      </p>
      <div class="mt-6 flex w-full flex-col gap-2">
        <v-btn
          size="large"
          color="primary"
          :to="`/issues/${created.id}`"
          prepend-icon="mdi-eye-outline"
        >
          Открыть заявку
        </v-btn>
        <v-btn size="large" variant="text" to="/">На главную</v-btn>
      </div>
    </section>

    <template v-else>
      <div class="mb-4 flex items-center gap-3" aria-live="polite">
        <div class="step" :class="{ 'step--on': step >= 1 }">
          <div class="step-dot" :class="{ 'step-dot--on': step >= 1 }">1</div>
          <span class="step__label">Описание</span>
        </div>
        <div class="h-0.5 min-w-4 flex-1 rounded bg-on-surface/10">
          <div
            class="h-full rounded bg-primary transition-all"
            :style="{ width: step === 2 ? '100%' : '0%' }"
          />
        </div>
        <div class="step" :class="{ 'step--on': step >= 2 }">
          <div class="step-dot" :class="{ 'step-dot--on': step >= 2 }">2</div>
          <span class="step__label">Место и отправка</span>
        </div>
        <span class="sr-only">Шаг {{ step }} из 2</span>
      </div>

      <!-- Шаг 1: что случилось -->
      <section v-if="step === 1">
        <h2 class="mt-0 mb-1 text-xl font-bold">Что случилось?</h2>
        <p class="text-muted mt-0 mb-3 text-sm">
          Опишите своими словами. Кузя сам поймёт, кто должен чинить.
        </p>
        <v-textarea
          v-model="description"
          label="Описание проблемы"
          placeholder="Например: на 9 этаже во втором подъезде течёт крыша, вода капает на лестницу"
          rows="4"
          auto-grow
          persistent-placeholder
          maxlength="2000"
          :hint="
            description.trim().length && !textOk
              ? `Напишите чуть подробнее: ещё ${MIN_TEXT - description.trim().length} ${plural(MIN_TEXT - description.trim().length, ['буква', 'буквы', 'букв'])}`
              : ''
          "
          persistent-hint
        />

        <!-- место под подсказку занято заранее: кнопка «Дальше» не съезжает, когда она появляется -->
        <div class="mt-2 min-h-[84px]" aria-live="polite">
          <div v-if="classifying || classification" class="kuzya-hint">
            <img src="/kuzya-avatar.png" alt="" width="36" height="36" class="kuzya-hint__face" />
            <p v-if="classifying" class="m-0">Кузя читает описание...</p>
            <p v-else-if="classification" class="m-0">
              Похоже, это <b>{{ classification.category_title }}</b
              >. Отвечает {{ orgTitle(classification.org_name) }}, срок
              {{ formatHours(classification.deadline_hours) }}
            </p>
          </div>
        </div>

        <h3 class="mt-5 mb-2 text-base font-bold">
          Фото <span class="text-muted font-normal">(необязательно)</span>
        </h3>
        <PhotoPicker v-model="photos" />

        <!-- подсказка скрывается, но место остаётся: кнопка не прыгает под пальцем -->
        <p class="text-muted mt-6 mb-2 text-center text-sm" :class="{ invisible: textOk }">
          Опишите проблему, чтобы продолжить
        </p>
        <v-btn
          block
          size="x-large"
          color="primary"
          class="sticky-cta"
          :disabled="!textOk"
          :loading="advancing"
          append-icon="mdi-arrow-right"
          @click="next"
        >
          Дальше
          <template #loader>Кузя ищет похожие...</template>
        </v-btn>

        <!-- Нашлась похожая заявка: главное действие - поддержать её, а не создать дубль -->
        <Drawer v-model:open="similarOpen">
          <DrawerContent>
            <DrawerHeader
              title="Похоже, об этом уже сообщили"
              description="Поддержите заявку соседа: так обращение уйдёт быстрее"
            />
            <section aria-label="Похожие заявки">
              <p v-if="similar.every((i) => i.voted_by_me)" class="mt-0 mb-1">
                Вы уже поддержали эту заявку, новую создавать не нужно. Кузя сообщит, когда её
                отправят.
              </p>
              <div v-for="item in similar" :key="item.id" class="similar">
                <router-link :to="`/issues/${item.id}`" class="similar__link">
                  <span class="font-semibold">{{ item.title }}</span>
                  <span class="text-muted text-sm">
                    {{ ISSUE_STATUS_TITLES[item.status] }} · {{ item.votes_count }} из
                    {{ item.votes_needed }}
                    {{ plural(item.votes_needed, ['голоса', 'голосов', 'голосов']) }}
                  </span>
                </router-link>
                <template v-if="item.status !== 'voting' || item.voted_by_me">
                  <div v-if="item.voted_by_me" class="voted mt-2" role="status">
                    <v-icon icon="mdi-check-circle" size="22" /> Вы уже поддержали эту заявку
                  </div>
                  <v-btn
                    class="mt-2"
                    color="primary"
                    variant="tonal"
                    size="large"
                    block
                    prepend-icon="mdi-eye-outline"
                    :to="`/issues/${item.id}`"
                  >
                    {{ item.status === 'voting' ? 'Открыть заявку' : 'Посмотреть, что с заявкой' }}
                  </v-btn>
                </template>
                <v-btn
                  v-else
                  class="mt-2"
                  color="primary"
                  size="x-large"
                  block
                  :loading="supporting === item.id"
                  prepend-icon="mdi-hand-back-right-outline"
                  @click="support(item)"
                >
                  Поддержать эту заявку
                </v-btn>
              </div>
            </section>

            <v-btn block size="large" variant="text" class="mt-2" @click="goStep2">
              Нет, у меня другая проблема
            </v-btn>
          </DrawerContent>
        </Drawer>
      </section>

      <!-- Шаг 2: уточнить и отправить -->
      <section v-else>
        <h2 class="mt-0 mb-1 text-xl font-bold">Почти готово</h2>
        <p class="text-muted mt-0 mb-3 text-sm">
          Уточните место, чтобы мастер нашёл быстрее. Можно пропустить.
        </p>
        <v-text-field
          v-model="locationHint"
          label="Где именно?"
          placeholder="Подъезд 2, 9 этаж"
          prepend-inner-icon="mdi-map-marker-outline"
          maxlength="200"
          class="mb-3"
        />
        <v-text-field
          v-model="title"
          label="Короткий заголовок"
          :placeholder="classification ? classification.category_title : 'Кузя придумает сам'"
          maxlength="120"
          hint="Если оставить пустым, Кузя придумает заголовок сам"
          persistent-hint
        />

        <div class="card-soft mt-4 p-4">
          <div class="text-muted text-sm">Что уйдёт соседям</div>
          <p class="pre-wrap line-clamp-2 mt-1 mb-2">{{ description }}</p>
          <div class="flex flex-wrap gap-2">
            <v-chip size="small" prepend-icon="mdi-image-multiple-outline">
              {{ photos.length }} фото
            </v-chip>
            <v-chip v-if="classification" size="small" prepend-icon="mdi-domain">
              {{ orgTitle(classification.org_name) }}
            </v-chip>
          </div>
        </div>

        <div v-if="submitting" class="mt-4" aria-live="polite">
          <v-progress-linear :model-value="progress" color="primary" height="10" />
          <div class="text-muted mt-1 text-sm">
            {{ progress < 100 ? `Отправляем... ${progress}%` : 'Кузя разбирает заявку...' }}
          </div>
        </div>

        <v-btn
          block
          size="x-large"
          color="primary"
          class="sticky-cta mt-5"
          prepend-icon="mdi-send"
          :loading="submitting"
          @click="submit"
        >
          Отправить
        </v-btn>
        <v-btn
          block
          variant="text"
          size="large"
          class="mt-1"
          :disabled="submitting"
          @click="step = 1"
        >
          Назад к описанию
        </v-btn>
      </section>
    </template>
  </div>
</template>

<style scoped>
.step {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.step__label {
  font-size: 0.875rem;
  font-weight: 600;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), var(--muted-alpha));
}
.step--on .step__label {
  color: rgb(var(--v-theme-on-surface));
}
/* Подсказка Кузи - отдельный «голос» помощника, а не серый служебный чип */
.kuzya-hint {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px 10px 10px;
  border-radius: var(--r-md);
  background: rgb(var(--v-theme-primary-container));
  color: rgb(var(--v-theme-on-primary-container));
  font-size: 0.95rem;
  line-height: 1.35;
}
.kuzya-hint__face {
  flex-shrink: 0;
  border-radius: 50%;
  background: rgb(var(--v-theme-surface));
}
.step-dot {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  font-weight: 700;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.step-dot--on {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
.similar {
  padding: 10px 0;
  border-top: 1px solid rgba(var(--v-border-color), 0.12);
}
.similar__link {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 44px;
  color: inherit;
  text-decoration: none;
}
</style>
