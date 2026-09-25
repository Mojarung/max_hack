<script setup lang="ts">
import { computed, onMounted, ref, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, errorMessage } from '@/api/client'
import { listingsApi } from '@/api/endpoints'
import type { ListingStatus } from '@/api/types'
import ErrorState from '@/components/common/ErrorState.vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import { Skeleton } from '@/components/ui/skeleton'
import { notify } from '@/lib/notify'
import { haptic } from '@/max/bridge'
import { useListingsStore } from '@/stores/listings'
import { formatPrice, formatRelative, fullName } from '@/utils/format'
import { LISTING_CATEGORY_ICONS, LISTING_STATUS_META } from '@/utils/labels'

const PhotoGallery = defineAsyncComponent(() => import('@/components/common/PhotoGallery.vue'))

const props = defineProps<{ id: number }>()
const store = useListingsStore()
const router = useRouter()

const loading = ref(false)
const error = ref<string | null>(null)
const notFound = ref(false)
const contactOpen = ref(false)
const message = ref('')
const sending = ref(false)
const statusSaving = ref<ListingStatus | null>(null)
const confirmDelete = ref(false)
const deleting = ref(false)

const STATUSES: ListingStatus[] = ['active', 'reserved', 'closed']
const listing = computed(() => store.details[props.id] ?? null)

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
onMounted(load)

function openContact(): void {
  message.value = listing.value?.is_free
    ? 'Здравствуйте! Можно забрать? Когда удобно?'
    : 'Здравствуйте! Ещё актуально?'
  contactOpen.value = true
}

async function send(): Promise<void> {
  if (!message.value.trim()) return
  sending.value = true
  try {
    await listingsApi.contact(props.id, message.value.trim())
    contactOpen.value = false
    notify.success('Кузя передал сообщение', 'Продавец получит его в личных сообщениях MAX')
  } catch (e) {
    notify.error(e, 'Сообщение не отправлено')
  } finally {
    sending.value = false
  }
}

async function setStatus(status: ListingStatus): Promise<void> {
  if (!listing.value || listing.value.status === status) return
  statusSaving.value = status
  haptic.selection()
  try {
    await store.setStatus(props.id, status)
    notify.success(`Статус: ${LISTING_STATUS_META[status].title.toLowerCase()}`)
  } catch (e) {
    notify.error(e, 'Статус не изменился')
  } finally {
    statusSaving.value = null
  }
}

async function remove(): Promise<void> {
  deleting.value = true
  try {
    await store.remove(props.id)
    confirmDelete.value = false
    notify.success('Объявление удалено')
    await router.replace('/market')
  } catch (e) {
    notify.error(e, 'Не удалось удалить')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="page">
    <div v-if="loading && !listing" aria-busy="true" aria-label="Загрузка">
      <Skeleton class="h-[260px] w-full rounded-2xl" />
      <Skeleton class="mt-4 h-7 w-1/3" />
      <Skeleton class="mt-2 h-5 w-3/4" />
    </div>

    <ErrorState
      v-else-if="error && !listing"
      :title="notFound ? 'Объявление не найдено' : 'Не получилось загрузить'"
      :message="error"
      :retrying="loading"
      @retry="load"
    />

    <article v-else-if="listing">
      <PhotoGallery :photos="listing.photos" :alt="listing.title" :height="280" />
      <div
        v-if="!listing.photos.length"
        class="flex h-[160px] items-center justify-center rounded-2xl bg-surface-variant"
      >
        <v-icon
          :icon="LISTING_CATEGORY_ICONS[listing.category] ?? 'mdi-shape-outline'"
          size="64"
          color="primary"
        />
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-2">
        <v-chip
          v-if="listing.status !== 'active'"
          :color="LISTING_STATUS_META[listing.status].color"
          :prepend-icon="LISTING_STATUS_META[listing.status].icon"
          size="small"
        >
          {{ LISTING_STATUS_META[listing.status].title }}
        </v-chip>
        <v-chip
          size="small"
          variant="outlined"
          :prepend-icon="LISTING_CATEGORY_ICONS[listing.category]"
        >
          {{ listing.category_title }}
        </v-chip>
      </div>
      <div class="mt-2 text-[28px] font-extrabold">
        {{ formatPrice(listing.price, listing.is_free) }}
      </div>
      <h2 class="mt-1 mb-0 text-xl leading-snug font-bold">{{ listing.title }}</h2>
      <p class="pre-wrap mt-3 mb-0 leading-relaxed">{{ listing.description }}</p>

      <router-link
        :to="`/people/${listing.author.id}`"
        class="card-soft tap-card mt-4 flex items-center gap-3 p-3 text-inherit no-underline"
        :aria-label="`Продавец: ${fullName(listing.author)}. Открыть профиль`"
      >
        <UserAvatar :user="listing.author" :size="44" />
        <div class="min-w-0 flex-1">
          <div class="font-semibold">{{ fullName(listing.author) }}</div>
          <div class="text-muted text-sm">
            <template v-if="listing.author?.apartment"
              >Квартира {{ listing.author.apartment }} ·
            </template>
            {{ formatRelative(listing.created_at) }}
          </div>
        </div>
        <v-icon icon="mdi-chevron-right" aria-hidden="true" />
      </router-link>

      <!-- Своё объявление -->
      <section
        v-if="listing.is_mine"
        class="card-soft mt-4 p-4"
        aria-label="Управление объявлением"
      >
        <h3 class="m-0 mb-1 text-base font-bold">Ваше объявление</h3>
        <p class="text-muted mt-0 mb-3 text-sm">
          Договорились с соседом - отметьте «Забронировано», отдали или продали - «Закрыто».
        </p>
        <div class="flex flex-col gap-2" role="radiogroup" aria-label="Статус объявления">
          <v-btn
            v-for="s in STATUSES"
            :key="s"
            :color="listing.status === s ? LISTING_STATUS_META[s].color : undefined"
            :variant="listing.status === s ? 'flat' : 'outlined'"
            :loading="statusSaving === s"
            role="radio"
            size="large"
            :aria-checked="listing.status === s"
            :prepend-icon="listing.status === s ? 'mdi-radiobox-marked' : 'mdi-radiobox-blank'"
            class="justify-start"
            @click="setStatus(s)"
          >
            {{ LISTING_STATUS_META[s].title }}
          </v-btn>
        </div>
        <v-btn
          block
          variant="text"
          color="error"
          class="mt-3"
          prepend-icon="mdi-delete-outline"
          @click="confirmDelete = true"
        >
          Удалить объявление
        </v-btn>
      </section>

      <v-btn
        v-else
        block
        size="x-large"
        color="primary"
        class="mt-5"
        prepend-icon="mdi-message-text-outline"
        :disabled="listing.status === 'closed'"
        @click="openContact"
      >
        {{
          listing.status === 'closed'
            ? 'Объявление закрыто'
            : listing.is_free
              ? 'Хочу забрать'
              : 'Написать продавцу'
        }}
      </v-btn>

      <Drawer v-model:open="contactOpen">
        <DrawerContent>
          <DrawerHeader
            :title="listing.is_free ? 'Сообщение автору' : 'Сообщение продавцу'"
            :description="`Кузя передаст сообщение в личку MAX. Продавец: ${fullName(listing.author)}`"
          />
          <v-textarea
            v-model="message"
            label="Ваше сообщение"
            rows="3"
            auto-grow
            maxlength="500"
            counter="500"
          />
          <v-btn
            block
            size="large"
            color="primary"
            class="mt-3"
            prepend-icon="mdi-send"
            :loading="sending"
            :disabled="!message.trim()"
            @click="send"
          >
            Отправить
          </v-btn>
        </DrawerContent>
      </Drawer>

      <v-dialog v-model="confirmDelete" max-width="400">
        <v-card
          rounded="xl"
          title="Удалить объявление?"
          text="Его больше никто не увидит. Это нельзя отменить."
        >
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="confirmDelete = false">Отмена</v-btn>
            <v-btn color="error" variant="flat" :loading="deleting" @click="remove">Удалить</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </article>
  </div>
</template>
