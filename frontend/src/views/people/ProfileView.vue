<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ApiError, errorMessage } from '@/api/client'
import { houseApi, peopleApi } from '@/api/endpoints'
import type { ProfileOut } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import AvatarPicker from '@/components/common/AvatarPicker.vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import { Skeleton } from '@/components/ui/skeleton'
import { notify } from '@/lib/notify'
import { haptic, openMaxLink } from '@/max/bridge'
import { useSessionStore } from '@/stores/session'
import { formatDate, fullName, plural } from '@/utils/format'

const props = defineProps<{ id: number }>()
const session = useSessionStore()
const profile = ref<ProfileOut | null>(null)
const error = ref<string | null>(null)
const notFound = ref(false)
const loading = ref(false)
const apartment = ref('')
const savingApt = ref(false)
const pickerOpen = ref(false)
const thanking = ref(false)
const messageOpen = ref(false)
const messageText = ref('')
const sending = ref(false)

const stats = computed(() => {
  const s = profile.value?.stats
  if (!s) return []
  return [
    {
      icon: 'mdi-bullhorn-outline',
      value: s.issues_created,
      label: plural(s.issues_created, ['заявка', 'заявки', 'заявок']),
    },
    {
      icon: 'mdi-thumb-up-outline',
      value: s.votes,
      label: plural(s.votes, ['голос за соседей', 'голоса за соседей', 'голосов за соседей']),
    },
    {
      icon: 'mdi-calendar-check-outline',
      value: s.events_joined,
      label: plural(s.events_joined, ['событие', 'события', 'событий']),
    },
    {
      icon: 'mdi-storefront-outline',
      value: s.listings_active,
      label: plural(s.listings_active, ['объявление', 'объявления', 'объявлений']),
    },
  ]
})

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    profile.value = await peopleApi.profile(props.id)
    apartment.value = profile.value.user.apartment ?? ''
  } catch (e) {
    notFound.value = e instanceof ApiError && e.status === 404
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const aptChanged = computed(
  () => !!profile.value?.is_me && apartment.value.trim() !== (profile.value.user.apartment ?? ''),
)

// «Назад» не должен молча терять введённый номер квартиры: сохраняем сами
onBeforeRouteLeave(async () => {
  if (aptChanged.value) await saveApartment()
})

async function saveApartment(): Promise<void> {
  if (!aptChanged.value) return
  savingApt.value = true
  try {
    session.me = await houseApi.update({ apartment: apartment.value.trim() })
    if (profile.value) profile.value.user.apartment = apartment.value.trim() || null
    notify.success('Квартира сохранена', 'Соседи увидят её в вашем профиле')
  } catch (e) {
    notify.error(e)
  } finally {
    savingApt.value = false
  }
}

/** Есть ник в MAX - открываем чат с соседом, нет - Кузя перешлёт сообщение ему в личку. */
function write(): void {
  const username = profile.value?.username
  if (username) openMaxLink(`https://max.ru/${username}`)
  else messageOpen.value = true
}

async function sendMessage(): Promise<void> {
  if (!profile.value || !messageText.value.trim()) return
  sending.value = true
  try {
    await peopleApi.message(profile.value.user.id, messageText.value.trim())
    messageOpen.value = false
    messageText.value = ''
    notify.success('Кузя передал сообщение', 'Сосед ответит вам в личных сообщениях MAX')
  } catch (e) {
    notify.error(e, 'Не удалось отправить')
  } finally {
    sending.value = false
  }
}

async function thank(): Promise<void> {
  if (!profile.value || thanking.value) return
  thanking.value = true
  try {
    profile.value = await peopleApi.thank(profile.value.user.id)
    haptic.notify('success')
    notify.success('Спасибо отправлено', 'Сосед получил +5 очков')
  } catch (e) {
    notify.error(e)
  } finally {
    thanking.value = false
  }
}
</script>

<template>
  <div class="page">
    <EmptyState
      v-if="notFound"
      title="Житель не найден"
      text="Возможно, он уже не состоит в чате дома"
      mood="worried"
    >
      <v-btn to="/people" color="primary" size="large">Все соседи</v-btn>
    </EmptyState>
    <ErrorState v-else-if="error" :message="error" :retrying="loading" @retry="load" />
    <div v-else-if="!profile" class="flex flex-col gap-3">
      <Skeleton class="h-[120px] rounded-[20px]" />
      <Skeleton class="h-[160px] rounded-[20px]" />
    </div>
    <template v-else>
      <section class="card-soft flex flex-wrap items-center gap-x-4 gap-y-3 p-4">
        <button
          v-if="profile.is_me"
          type="button"
          class="avatar-edit"
          aria-label="Сменить аватарку"
          @click="pickerOpen = true"
        >
          <UserAvatar :user="profile.user" :size="72" />
          <span class="avatar-edit__badge" aria-hidden="true">
            <v-icon icon="mdi-pencil" size="16" />
          </span>
        </button>
        <UserAvatar v-else :user="profile.user" :size="72" />
        <div class="min-w-0 flex-1">
          <h2 class="m-0 text-xl leading-tight font-bold">{{ fullName(profile.user) }}</h2>
          <div class="text-muted mt-1">
            <template v-if="profile.user.apartment"
              >Квартира {{ profile.user.apartment }} · </template
            >в доме с {{ formatDate(profile.member_since) }}
          </div>
          <v-btn
            v-if="profile.is_me"
            variant="text"
            color="primary"
            class="mt-1 -ml-3"
            prepend-icon="mdi-account-circle-outline"
            @click="pickerOpen = true"
          >
            Сменить аватарку
          </v-btn>
        </div>
        <div class="badges basis-full">
          <span v-if="profile.user.role === 'admin'" class="badge badge--role">
            <v-icon icon="mdi-shield-account" size="16" aria-hidden="true" />
            администратор дома
          </span>
          <span class="badge">
            <v-icon icon="mdi-star-four-points" size="16" aria-hidden="true" />
            уровень {{ profile.level }} · {{ profile.user.level_title }}
          </span>
          <span class="badge badge--plain tabular-nums">
            {{ profile.user.points }} {{ plural(profile.user.points, ['очко', 'очка', 'очков']) }}
          </span>
        </div>
        <div v-if="!profile.is_me" class="actions basis-full">
          <v-btn color="primary" size="large" prepend-icon="mdi-message-outline" @click="write">
            Написать
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            size="large"
            prepend-icon="mdi-hand-heart-outline"
            :loading="thanking"
            :disabled="profile.thanked_by_me"
            @click="thank"
          >
            {{ profile.thanked_by_me ? 'Спасибо сказано' : 'Спасибо +5' }}
          </v-btn>
        </div>
        <p v-if="profile.thanks_count" class="text-muted m-0 basis-full text-sm">
          Соседи сказали спасибо {{ profile.thanks_count }}
          {{ plural(profile.thanks_count, ['раз', 'раза', 'раз']) }}
        </p>
      </section>
      <AvatarPicker v-if="profile.is_me" v-model:open="pickerOpen" @changed="load" />

      <section v-if="profile.is_me" class="card-soft mt-3 p-4" aria-labelledby="apt-title">
        <h2 id="apt-title" class="m-0 text-base font-bold">Моя квартира</h2>
        <p class="text-muted mt-1 mb-3 text-sm">По номеру квартиры соседям проще узнать вас</p>
        <form class="flex flex-col gap-2" @submit.prevent="saveApartment">
          <v-text-field
            v-model="apartment"
            label="Номер квартиры"
            inputmode="numeric"
            maxlength="16"
            hint="Можно не указывать"
            persistent-hint
            @blur="saveApartment"
          />
          <v-btn
            type="submit"
            block
            color="primary"
            size="large"
            :variant="aptChanged ? 'flat' : 'tonal'"
            :loading="savingApt"
          >
            Сохранить
          </v-btn>
        </form>
      </section>

      <h2 class="section-title">Помощь дому</h2>
      <section class="grid grid-cols-2 gap-3">
        <div v-for="s in stats" :key="s.label" class="card-soft flex flex-col gap-1 p-3">
          <v-icon :icon="s.icon" color="primary" size="24" aria-hidden="true" />
          <strong class="text-[28px] leading-none tabular-nums">{{ s.value }}</strong>
          <span class="text-muted text-sm leading-tight">{{ s.label }}</span>
        </div>
      </section>

      <template v-if="profile.achievements.length">
        <h2 class="section-title">Награды</h2>
        <div class="flex flex-wrap gap-2">
          <v-chip
            v-for="a in profile.achievements"
            :key="a.code"
            size="large"
            color="primary"
            variant="tonal"
            :prepend-icon="a.icon"
          >
            {{ a.title }}
          </v-chip>
        </div>
      </template>
    </template>

    <Drawer v-model:open="messageOpen">
      <DrawerContent>
        <DrawerHeader
          :title="`Написать: ${profile ? fullName(profile.user) : ''}`"
          description="Кузя перешлёт сообщение соседу в личные сообщения MAX. Ваш номер он не увидит"
        />
        <form class="flex flex-col gap-3" @submit.prevent="sendMessage">
          <v-textarea
            v-model="messageText"
            label="Сообщение"
            rows="3"
            auto-grow
            maxlength="1000"
            autofocus
          />
          <v-btn
            type="submit"
            block
            size="x-large"
            color="primary"
            prepend-icon="mdi-send"
            :loading="sending"
            :disabled="!messageText.trim()"
          >
            Отправить
          </v-btn>
        </form>
      </DrawerContent>
    </Drawer>
  </div>
</template>

<style scoped>
.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 600;
  color: rgb(var(--v-theme-on-primary-container));
  background: rgb(var(--v-theme-primary-container));
}
.badge--role {
  color: rgb(var(--v-theme-on-secondary-container));
  background: rgb(var(--v-theme-secondary-container));
}
.badge--plain {
  color: rgba(var(--v-theme-on-surface), var(--muted-alpha));
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.avatar-edit {
  position: relative;
  flex-shrink: 0;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: none;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.avatar-edit:focus-visible {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: 3px;
}
.avatar-edit__badge {
  position: absolute;
  right: -2px;
  bottom: -2px;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  color: rgb(var(--v-theme-on-primary));
  background: rgb(var(--v-theme-primary));
  border: 3px solid rgb(var(--v-theme-surface));
}
</style>
