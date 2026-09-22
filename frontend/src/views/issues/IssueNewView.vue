<script setup lang="ts">
import { watchDebounced } from '@vueuse/core'
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { issuesApi } from '@/api/endpoints'
import type { Classification, IssueDetail, IssueOut } from '@/api/types'
import PhotoPicker from '@/components/common/PhotoPicker.vue'
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import { useDirtyGuard } from '@/composables/useDirtyGuard'
import { confetti, pageEnter } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { haptic } from '@/max/bridge'
import { useIssuesStore } from '@/stores/issues'
import { plural } from '@/utils/format'

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

let analyzeController: AbortController | null = null

watchDebounced(
  description,
  async (text) => {
    analyzeController?.abort()
    const trimmed = text.trim()
    if (trimmed.length < 8) {
      classification.value = null
      similar.value = []
      return
    }
    const controller = new AbortController()
    analyzeController = controller
    classifying.value = true
    const [cls, sim] = await Promise.allSettled([
      issuesApi.classify(trimmed, controller.signal),
      issuesApi.similar(trimmed, controller.signal),
    ])
    if (controller.signal.aborted) return
    classifying.value = false
    if (cls.status === 'fulfilled') classification.value = cls.value
    if (sim.status === 'fulfilled') {
      similar.value = sim.value
        .filter((i) => i.status === 'voting' || i.status === 'sent' || i.status === 'in_progress')
        .slice(0, 3)
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
    notify.success('Голос учтён!', 'Вместе быстрее: Кузя учтёт вас в обращении')
    await router.replace(`/issues/${issue.id}`)
  } catch (e) {
    notify.error(e, 'Не удалось проголосовать')
  } finally {
    supporting.value = null
  }
}

function next(): void {
  if (!textOk.value) return
  haptic.impact('light')
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
      <KuzyaMascot mood="happy" :size="150" />
      <h2 class="mt-4 mb-2 text-2xl font-bold">Спасибо! Кузя всё записал</h2>
      <p class="text-muted m-0 max-w-[340px]">
        <template v-if="created.status === 'voting'">
          Соседи увидят проблему и смогут её поддержать. Нужно
          {{ created.votes_needed }}
          {{ plural(created.votes_needed, ['голос', 'голоса', 'голосов']) }}, и обращение уйдёт в
          {{ created.responsible_org?.name ?? 'управляющую компанию' }}.
        </template>
        <template v-else>Обращение уже отправлено ответственной организации.</template>
      </p>
      <div class="mt-6 flex w-full flex-col gap-2">
        <v-btn
          size="large"
          color="primary"
          :to="`/issues/${created.id}`"
          prepend-icon="mdi-eye-outline"
        >
          Открыть проблему
        </v-btn>
        <v-btn size="large" variant="text" to="/">На главную</v-btn>
      </div>
    </section>

    <template v-else>
      <div class="mb-4 flex items-center gap-3" aria-live="polite">
        <div class="step-dot" :class="{ 'step-dot--on': step >= 1 }">1</div>
        <div class="h-0.5 flex-1 rounded bg-on-surface/10">
          <div
            class="h-full rounded bg-primary transition-all"
            :style="{ width: step === 2 ? '100%' : '0%' }"
          />
        </div>
        <div class="step-dot" :class="{ 'step-dot--on': step >= 2 }">2</div>
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
          counter="2000"
          maxlength="2000"
          :hint="
            description.trim().length && !textOk
              ? `Ещё хотя бы ${MIN_TEXT - description.trim().length} симв.`
              : ''
          "
          persistent-hint
        />

        <div class="mt-2 min-h-[36px]" aria-live="polite">
          <v-chip
            v-if="classifying"
            color="secondary"
            variant="tonal"
            prepend-icon="mdi-head-cog-outline"
          >
            Кузя думает...
          </v-chip>
          <v-chip
            v-else-if="classification"
            color="secondary"
            variant="tonal"
            prepend-icon="mdi-lightbulb-on-outline"
            class="h-auto! py-1.5! whitespace-normal!"
          >
            Кузя думает: {{ classification.category_title }} → {{ classification.org_name }}, срок
            {{ classification.deadline_hours }} ч
          </v-chip>
        </div>

        <v-alert
          v-if="similar.length"
          type="info"
          variant="tonal"
          class="mt-3"
          rounded="xl"
          icon="mdi-account-group-outline"
          title="Похоже, об этом уже сообщили"
        >
          <p class="mt-1 mb-2 text-sm">
            Поддержите существующую заявку: так обращение уйдёт быстрее.
          </p>
          <div v-for="item in similar" :key="item.id" class="similar">
            <router-link :to="`/issues/${item.id}`" class="text-inherit font-semibold">{{
              item.title
            }}</router-link>
            <div class="text-muted text-sm">
              {{ item.status_title }} · {{ item.votes_count }} из {{ item.votes_needed }}
              {{ plural(item.votes_needed, ['голоса', 'голосов', 'голосов']) }}
            </div>
            <v-btn
              class="mt-2"
              color="primary"
              variant="flat"
              block
              :loading="supporting === item.id"
              :prepend-icon="item.voted_by_me ? 'mdi-check' : 'mdi-hand-back-right-outline'"
              @click="support(item)"
            >
              {{ item.voted_by_me ? 'Вы уже поддержали, открыть' : 'Поддержать голосом' }}
            </v-btn>
          </div>
        </v-alert>

        <h3 class="mt-5 mb-2 text-base font-bold">
          Фото <span class="text-muted font-normal">(необязательно)</span>
        </h3>
        <PhotoPicker v-model="photos" />

        <v-btn
          block
          size="x-large"
          color="primary"
          class="sticky-cta mt-6"
          :disabled="!textOk"
          append-icon="mdi-arrow-right"
          @click="next"
        >
          Дальше
        </v-btn>
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
            <v-chip v-if="classification" size="small" color="secondary" prepend-icon="mdi-domain">
              {{ classification.org_name }}
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
</style>
