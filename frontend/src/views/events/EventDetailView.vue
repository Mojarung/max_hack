<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, ref, watch } from 'vue'
import { ApiError, errorMessage } from '@/api/client'
import ErrorState from '@/components/common/ErrorState.vue'
import PhotoPicker from '@/components/common/PhotoPicker.vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import { Skeleton } from '@/components/ui/skeleton'
import { pop, staggerIn } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { haptic } from '@/max/bridge'
import { useEventsStore } from '@/stores/events'
import { useSessionStore } from '@/stores/session'
import { formatDateTime, formatRelative, fullName, pluralize } from '@/utils/format'
import { eventKindMeta } from '@/utils/labels'

const PhotoGallery = defineAsyncComponent(() => import('@/components/common/PhotoGallery.vue'))

// Фото у события не больше пяти, как у вещей (EventOut на бэкенде)
const MAX_EVENT_PHOTOS = 5

const props = defineProps<{ id: number }>()
const store = useEventsStore()
const session = useSessionStore()

const loading = ref(false)
const error = ref<string | null>(null)
const notFound = ref(false)
const joining = ref(false)
const joinBtn = ref<{ $el: HTMLElement } | null>(null)

const commentsLoading = ref(false)
const commentsError = ref<string | null>(null)
const text = ref('')
const sending = ref(false)
const rejected = ref<string | null>(null)
const commentsBox = ref<HTMLElement | null>(null)

const event = computed(() => store.details[props.id] ?? null)
const comments = computed(() => store.comments[props.id] ?? [])
const isPast = computed(() =>
  event.value ? Date.parse(event.value.starts_at) < Date.now() : false,
)
const isFull = computed(
  () =>
    !!event.value?.max_participants &&
    !event.value.joined_by_me &&
    event.value.participants_count >= event.value.max_participants,
)
const meId = computed(() => session.me?.user.id)
// Описание и фото дописывает организатор (или администратор дома), пока событие не прошло
const canEdit = computed(
  () => !!event.value && !isPast.value && (event.value.author.id === meId.value || session.isAdmin),
)
const photos = computed(() => event.value?.photos ?? [])

const editOpen = ref(false)
const draft = ref('')
const newPhotos = ref<File[]>([])
const saving = ref(false)
const removing = ref<number | null>(null)

function openEdit(): void {
  draft.value = event.value?.description ?? ''
  newPhotos.value = []
  editOpen.value = true
}

async function saveEdit(): Promise<void> {
  if (!event.value || saving.value) return
  saving.value = true
  try {
    if (draft.value.trim() !== event.value.description)
      await store.updateDescription(props.id, draft.value)
    if (newPhotos.value.length) await store.addPhotos(props.id, newPhotos.value)
    editOpen.value = false
    haptic.notify('success')
    notify.success('Сохранено, соседи увидят обновление')
  } catch (e) {
    notify.error(e, 'Не удалось сохранить')
  } finally {
    saving.value = false
  }
}

async function removePhoto(index: number): Promise<void> {
  removing.value = index
  try {
    await store.removePhoto(props.id, index)
  } catch (e) {
    notify.error(e, 'Фото не удалилось')
  } finally {
    removing.value = null
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    await store.fetchDetail(props.id)
  } catch (e) {
    notFound.value = e instanceof ApiError && e.status === 404
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function loadComments(): Promise<void> {
  commentsLoading.value = true
  commentsError.value = null
  try {
    await store.loadComments(props.id)
  } catch (e) {
    commentsError.value = errorMessage(e)
  } finally {
    commentsLoading.value = false
  }
}

onMounted(() => {
  void load()
  void loadComments()
})

watch(
  () => comments.value.length,
  () => nextTick(() => staggerIn(commentsBox.value, '[data-comment]')),
  { flush: 'post' },
)

async function toggleJoin(): Promise<void> {
  if (!event.value || joining.value) return
  joining.value = true
  haptic.impact('medium')
  const willJoin = !event.value.joined_by_me
  try {
    await store.toggleJoin(props.id)
    pop(joinBtn.value?.$el)
    notify.success(
      willJoin ? 'Вы идёте! Кузя напомнит заранее' : 'Запись отменена. Передумаете - нажмите «Иду»',
    )
  } catch (e) {
    notify.error(e, 'Не удалось сохранить')
  } finally {
    joining.value = false
  }
}

async function send(): Promise<void> {
  const value = text.value.trim()
  if (!value || sending.value) return
  sending.value = true
  rejected.value = null
  try {
    await store.addComment(props.id, value)
    text.value = ''
    haptic.impact('light')
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) {
      rejected.value = e.detail
      haptic.notify('warning')
    } else {
      notify.error(e, 'Комментарий не отправлен')
    }
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="page">
    <div v-if="loading && !event" aria-busy="true" aria-label="Загрузка">
      <Skeleton class="h-[140px] w-full rounded-2xl" />
      <Skeleton class="mt-4 h-6 w-3/4" />
      <Skeleton class="mt-2 h-4 w-1/2" />
    </div>

    <ErrorState
      v-else-if="error && !event"
      :title="notFound ? 'Событие не найдено' : 'Не получилось загрузить'"
      :message="error"
      :retrying="loading"
      @retry="load"
    />

    <article v-else-if="event">
      <PhotoGallery
        v-if="photos.length"
        :photos="photos"
        :alt="event.title"
        :height="220"
        class="mb-3"
      />
      <header
        class="event-hero"
        :style="{ '--kind': `var(--v-theme-${eventKindMeta(event.kind).color})` }"
      >
        <v-icon :icon="eventKindMeta(event.kind).icon" size="44" />
        <div class="mt-2 text-sm font-semibold opacity-90">{{ event.kind_title }}</div>
        <h2 class="m-0 text-[22px] leading-tight font-bold">{{ event.title }}</h2>
      </header>

      <ul class="card-soft mt-3 mb-0 flex list-none flex-col gap-3 p-4">
        <li class="flex items-start gap-3">
          <v-icon icon="mdi-calendar-clock" color="primary" />
          <div>
            <div class="font-semibold">{{ formatDateTime(event.starts_at) }}</div>
            <div v-if="isPast" class="text-muted text-sm">Событие уже прошло</div>
          </div>
        </li>
        <li class="flex items-start gap-3">
          <v-icon icon="mdi-map-marker-outline" color="primary" />
          <span class="font-semibold">{{ event.place }}</span>
        </li>
        <li class="flex items-start gap-3">
          <v-icon icon="mdi-account-outline" color="primary" />
          <span>Организатор: {{ fullName(event.author) }}</span>
        </li>
      </ul>

      <p v-if="event.description" class="pre-wrap mt-4 mb-0 leading-relaxed">
        {{ event.description }}
      </p>
      <!-- Событие из чата приходит без подробностей: организатору подсказываем их дописать -->
      <button
        v-if="canEdit && !event.description && !photos.length"
        type="button"
        class="add-details tap-card mt-4"
        @click="openEdit"
      >
        <v-icon icon="mdi-text-box-plus-outline" size="28" color="primary" />
        <span class="text-left">
          <span class="block font-semibold">Добавьте подробности и фото</span>
          <span class="text-muted block text-sm">Что взять с собой, где собираемся, кого ждём</span>
        </span>
      </button>
      <v-btn
        v-else-if="canEdit"
        variant="text"
        color="primary"
        prepend-icon="mdi-pencil-outline"
        class="mt-2 -ml-3"
        @click="openEdit"
      >
        Изменить описание и фото
      </v-btn>

      <section class="card-soft mt-4 p-4" aria-label="Участники">
        <div class="flex items-baseline justify-between">
          <h3 class="m-0 text-base font-bold">
            {{ pluralize(event.participants_count, ['участник', 'участника', 'участников']) }}
          </h3>
          <span v-if="event.max_participants" class="text-muted text-sm">
            свободно {{ Math.max(0, event.max_participants - event.participants_count) }} из
            {{ event.max_participants }}
          </span>
        </div>
        <div v-if="event.participants.length" class="mt-3 flex flex-wrap gap-1.5">
          <UserAvatar
            v-for="p in event.participants.slice(0, 16)"
            :key="p.id"
            :user="p"
            :size="38"
          />
          <v-avatar v-if="event.participants.length > 16" size="38" color="surface-variant">
            +{{ event.participants.length - 16 }}
          </v-avatar>
        </div>
        <p v-else class="text-muted mt-2 mb-0 text-sm">Пока никто не отметился. Будьте первым!</p>
        <template v-if="!isPast">
          <template v-if="event.joined_by_me">
            <div class="joined mt-4" role="status">
              <v-icon icon="mdi-check-circle" size="26" />
              Вы идёте. Кузя напомнит за пару часов
            </div>
            <v-btn
              block
              variant="text"
              size="large"
              class="mt-1"
              :loading="joining"
              @click="toggleJoin"
            >
              Не смогу прийти
            </v-btn>
          </template>
          <v-btn
            v-else
            ref="joinBtn"
            block
            size="x-large"
            class="mt-4"
            color="primary"
            prepend-icon="mdi-hand-wave-outline"
            :loading="joining"
            :disabled="isFull"
            @click="toggleJoin"
          >
            {{ isFull ? 'Мест нет' : 'Иду' }}
          </v-btn>
        </template>
      </section>

      <!-- Комментарии -->
      <section class="mt-4" aria-label="Обсуждение">
        <h3 class="section-title !mt-2">Обсуждение</h3>
        <div v-if="commentsLoading && !comments.length" class="flex flex-col gap-2">
          <Skeleton v-for="i in 3" :key="i" class="h-14 w-4/5 rounded-2xl" />
        </div>
        <div v-else-if="commentsError && !comments.length" class="text-muted text-sm" role="alert">
          {{ commentsError }}
          <v-btn variant="text" size="small" color="primary" @click="loadComments">Повторить</v-btn>
        </div>
        <p v-else-if="!comments.length" class="text-muted m-0 text-sm">
          Пока тихо. Спросите, что взять с собой, или договоритесь о деталях.
        </p>
        <div ref="commentsBox" class="flex flex-col gap-2" aria-live="polite">
          <div
            v-for="c in comments"
            :key="c.id"
            data-comment
            class="flex items-end gap-2"
            :class="{ 'flex-row-reverse': c.author?.id === meId }"
          >
            <UserAvatar :user="c.author" :size="30" />
            <div class="bubble" :class="{ 'bubble--mine': c.author?.id === meId }">
              <div v-if="c.author?.id !== meId" class="text-sm font-semibold text-primary">
                {{ fullName(c.author) }}
              </div>
              <div class="pre-wrap">{{ c.text }}</div>
              <div class="text-muted mt-0.5 text-right text-sm">
                {{ formatRelative(c.created_at) }}
              </div>
            </div>
          </div>
        </div>

        <v-alert
          v-if="rejected"
          type="warning"
          variant="tonal"
          rounded="lg"
          class="mt-3"
          icon="mdi-shield-alert-outline"
          closable
          @click:close="rejected = null"
        >
          Кузя не пропустил: {{ rejected }}
        </v-alert>

        <form class="composer mt-3" @submit.prevent="send">
          <v-textarea
            v-model="text"
            placeholder="Написать комментарий"
            rows="1"
            auto-grow
            max-rows="5"
            maxlength="1000"
            density="comfortable"
            hide-details
            aria-label="Текст комментария"
            @keydown.enter.exact.prevent="send"
          />
          <v-btn
            type="submit"
            icon="mdi-send"
            color="primary"
            size="large"
            :loading="sending"
            :disabled="!text.trim()"
            aria-label="Отправить комментарий"
          />
        </form>
      </section>
    </article>

    <Drawer v-model:open="editOpen">
      <DrawerContent>
        <DrawerHeader
          title="Подробности события"
          description="Соседи увидят описание и фото на странице события"
        />
        <v-textarea
          v-model="draft"
          label="Описание"
          placeholder="Например: возьмите перчатки, мешки и грабли даёт УК. После уборки чай у 2 подъезда"
          persistent-placeholder
          rows="3"
          auto-grow
          maxlength="2000"
        />
        <template v-if="photos.length">
          <h4 class="mt-2 mb-2 text-base font-bold">Фото события</h4>
          <ul class="mb-3 flex list-none flex-wrap gap-2 p-0">
            <li v-for="(src, i) in photos" :key="src" class="relative">
              <img :src="src" alt="" class="h-20 w-20 rounded-2xl object-cover" />
              <v-btn
                icon="mdi-close"
                size="small"
                class="!absolute -top-2 -right-2"
                :loading="removing === i"
                :aria-label="`Удалить фото ${i + 1}`"
                @click="removePhoto(i)"
              />
            </li>
          </ul>
        </template>
        <PhotoPicker
          v-if="photos.length < MAX_EVENT_PHOTOS"
          v-model="newPhotos"
          :max="MAX_EVENT_PHOTOS - photos.length"
        />
        <v-btn
          block
          size="large"
          color="primary"
          class="mt-4"
          :loading="saving"
          :disabled="draft.trim() === event?.description && !newPhotos.length"
          @click="saveEdit"
        >
          Сохранить
        </v-btn>
      </DrawerContent>
    </Drawer>
  </div>
</template>

<style scoped>
.event-hero {
  padding: 20px 16px;
  border-radius: var(--radius-card);
  color: rgb(var(--v-theme-on-surface));
  /* тональная шапка цвета типа события: заливка остаётся только у тревоги и главной кнопки */
  background: rgba(var(--kind), 0.14);
  border: 1px solid rgba(var(--kind), 0.3);
}
.event-hero :deep(.v-icon) {
  color: rgb(var(--kind));
}
.add-details {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  border: 1.5px dashed rgba(var(--v-theme-primary), 0.45);
  border-radius: var(--r-lg);
  background: rgba(var(--v-theme-primary), 0.05);
  color: inherit;
  font: inherit;
}
.bubble {
  max-width: 78%;
  padding: 8px 12px;
  border-radius: 20px 20px 20px 6px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), 0.1);
}
.bubble--mine {
  border-radius: 20px 20px 6px 20px;
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: transparent;
}
.composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.composer > :first-child {
  flex: 1;
}
</style>
