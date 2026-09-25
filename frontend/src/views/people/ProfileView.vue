<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiError, errorMessage } from '@/api/client'
import { houseApi, peopleApi } from '@/api/endpoints'
import type { ProfileOut } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import { Skeleton } from '@/components/ui/skeleton'
import { notify } from '@/lib/notify'
import { openMaxLink } from '@/max/bridge'
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

async function saveApartment(): Promise<void> {
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

function writeInMax(): void {
  const username = profile.value?.username
  if (username) openMaxLink(`https://max.ru/${username}`)
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
      <section class="card-soft flex items-center gap-4 p-4">
        <UserAvatar :user="profile.user" :size="72" />
        <div class="min-w-0 flex-1">
          <h2 class="m-0 text-xl leading-tight font-bold">{{ fullName(profile.user) }}</h2>
          <div class="text-muted mt-1">
            <template v-if="profile.user.apartment"
              >Квартира {{ profile.user.apartment }} ·
            </template>
            {{ profile.user.role === 'admin' ? 'администратор дома' : 'житель' }}
          </div>
          <div class="text-muted text-sm">В доме с {{ formatDate(profile.member_since) }}</div>
        </div>
      </section>

      <section class="card-soft mt-3 p-4" aria-label="Уровень">
        <div class="flex items-center gap-3">
          <v-avatar color="primary" size="44"
            ><span class="text-lg font-bold">{{ profile.level }}</span></v-avatar
          >
          <div class="min-w-0 flex-1">
            <div class="font-semibold">«{{ profile.user.level_title }}»</div>
            <div class="text-muted text-sm tabular-nums">
              {{ profile.user.points }} {{ plural(profile.user.points, ['очко', 'очка', 'очков']) }}
            </div>
          </div>
        </div>
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

      <template v-if="profile.is_me">
        <h2 class="section-title">Моя квартира</h2>
        <form class="flex gap-2" @submit.prevent="saveApartment">
          <v-text-field
            v-model="apartment"
            label="Номер квартиры"
            inputmode="numeric"
            maxlength="16"
            hint="Необязательно. Соседям проще узнать вас"
          />
          <v-btn
            type="submit"
            color="primary"
            size="x-large"
            variant="tonal"
            :loading="savingApt"
            aria-label="Сохранить квартиру"
            icon="mdi-check"
          />
        </form>
      </template>
      <v-btn
        v-else-if="profile.username"
        block
        size="x-large"
        color="primary"
        class="mt-4"
        prepend-icon="mdi-message-outline"
        @click="writeInMax"
      >
        Написать в MAX
      </v-btn>
    </template>
  </div>
</template>
