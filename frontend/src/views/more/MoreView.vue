<script setup lang="ts">
import { computed, ref } from 'vue'
import { BROWSER_DEMO } from '@/api/mode'
import UserAvatar from '@/components/common/UserAvatar.vue'
import HouseSwitcher from '@/components/house/HouseSwitcher.vue'
import { useStagger } from '@/composables/useMotion'
import { openMaxLink } from '@/max/bridge'
import { useSessionStore } from '@/stores/session'
import { fullName, pluralize } from '@/utils/format'

const session = useSessionStore()
const root = ref<HTMLElement | null>(null)
useStagger(root, () => session.me?.user.id)

interface Entry {
  to: string
  title: string
  subtitle: string
  icon: string
  color: string
}

const entries = computed<Entry[]>(() => {
  const list: Entry[] = [
    {
      to: '/more/house',
      title: 'О доме',
      subtitle: 'Адрес, управляющая компания, телефоны',
      icon: 'mdi-home-city-outline',
      color: 'primary',
    },
    {
      to: '/announcements',
      title: 'Объявления',
      subtitle: 'Отключения, работы, собрания',
      icon: 'mdi-bullhorn-variant-outline',
      color: 'warning',
    },
    {
      to: '/more/documents',
      title: 'Документы',
      subtitle: 'Протоколы собраний, договор, ваши квитанции',
      icon: 'mdi-file-document-multiple-outline',
      color: 'secondary',
    },
    {
      to: '/people',
      title: 'Соседи',
      subtitle: 'Профили жителей дома',
      icon: 'mdi-account-group-outline',
      color: 'tertiary',
    },
    {
      to: '/more/search',
      title: 'Поиск',
      subtitle: 'По заявкам, событиям и вещам соседей',
      icon: 'mdi-magnify',
      color: 'info',
    },
    {
      to: '/more/assistant',
      title: 'Спросить Кузю',
      subtitle: 'Ответит про заявки, сроки и события',
      icon: 'mdi-chat-processing-outline',
      color: 'primary',
    },
    {
      to: '/more/achievements',
      title: 'Награды и рейтинг',
      subtitle: 'Очки за помощь дому, место среди соседей',
      icon: 'mdi-trophy-outline',
      color: 'warning',
    },
  ]
  // в демо из браузера бота нет: чат с Кузей живёт в MAX
  if (session.canUseDevTools && !BROWSER_DEMO) {
    list.push({
      to: '/dev/chat',
      title: 'Эмулятор чата MAX',
      subtitle: 'Как Кузя отвечает в чате, без MAX',
      icon: 'mdi-message-cog-outline',
      color: 'secondary',
    })
  }
  if (session.canManageMcp) {
    list.push({
      to: '/more/mcp',
      title: 'Навыки Кузи',
      subtitle: 'Откуда Кузя берёт данные о доме',
      icon: 'mdi-puzzle-outline',
      color: 'muted',
    })
  }
  return list
})

function openBot(): void {
  const name = session.me?.bot_username
  if (name) openMaxLink(`https://max.ru/${name}`)
}
</script>

<template>
  <div ref="root" class="page">
    <!-- Профиль и дом одной группой, как карточка аккаунта в настройках iOS -->
    <div v-if="session.me" class="group-list" style="--group-inset: 16px" data-stagger>
      <router-link
        :to="`/people/${session.me.user.id}`"
        class="tap-row flex items-center gap-3 p-4 text-inherit no-underline"
        aria-label="Мой профиль"
      >
        <UserAvatar :user="session.me.user" :size="56" />
        <div class="min-w-0 flex-1">
          <div class="text-lg font-bold">{{ fullName(session.me.user) }}</div>
          <div class="text-muted text-sm">
            <template v-if="session.me.user.apartment"
              >Квартира {{ session.me.user.apartment }} ·
            </template>
            {{ session.me.user.level_title }} ·
            {{ pluralize(session.me.user.points, ['очко', 'очка', 'очков']) }}
          </div>
          <div v-if="!session.me.user.apartment" class="text-sm font-semibold text-primary">
            Укажите номер квартиры
          </div>
        </div>
        <v-icon icon="mdi-chevron-right" aria-hidden="true" />
      </router-link>
      <HouseSwitcher v-if="session.houses.length">
        <template #trigger="{ open }">
          <button type="button" class="tap-row house-row" @click="open">
            <v-icon icon="mdi-home-city-outline" color="primary" aria-hidden="true" />
            <span class="min-w-0 flex-1">
              <span class="text-muted block text-sm">{{
                session.houses.length > 1 ? 'Мой дом, нажмите, чтобы сменить' : 'Мой дом'
              }}</span>
              <span class="block truncate font-semibold">{{ session.me.house.title }}</span>
            </span>
            <v-icon icon="mdi-chevron-right" aria-hidden="true" />
          </button>
        </template>
      </HouseSwitcher>
    </div>

    <!-- Тревога - самое важное, что может понадобиться: сразу под профилем и красным -->
    <router-link
      to="/more/safety"
      class="safety card-soft tap-card mt-3 flex items-center gap-3 p-3 no-underline"
      data-stagger
    >
      <v-avatar color="deep" size="48" rounded="lg">
        <v-icon icon="mdi-shield-home-outline" size="26" />
      </v-avatar>
      <div class="min-w-0 flex-1">
        <div class="text-base font-bold">Безопасность</div>
        <div class="text-muted text-sm">Укрытия рядом и что делать при тревоге</div>
      </div>
      <v-icon icon="mdi-chevron-right" aria-hidden="true" />
    </router-link>

    <h2 class="section-title">Мой дом</h2>
    <nav class="group-list" style="--group-inset: 72px" aria-label="Разделы">
      <router-link
        v-for="e in entries"
        :key="e.to"
        :to="e.to"
        class="tap-row flex items-center gap-3 p-3 text-inherit no-underline"
      >
        <v-avatar :color="e.color" variant="tonal" size="48" rounded="lg">
          <v-icon :icon="e.icon" size="26" />
        </v-avatar>
        <div class="min-w-0 flex-1">
          <div class="text-base font-semibold">{{ e.title }}</div>
          <div class="text-muted text-sm">{{ e.subtitle }}</div>
        </div>
        <v-icon icon="mdi-chevron-right" />
      </router-link>
    </nav>

    <v-btn
      v-if="session.me?.bot_username"
      block
      size="large"
      variant="tonal"
      color="primary"
      class="mt-4"
      prepend-icon="mdi-robot-happy-outline"
      data-stagger
      @click="openBot"
    >
      Открыть чат с Кузей в MAX
    </v-btn>

    <p class="text-muted mt-6 text-center text-sm">
      Домовой Кузя · {{ session.inMax ? 'MAX' : 'демо-режим в браузере' }}
    </p>
  </div>
</template>

<style scoped>
.safety {
  color: inherit;
  border-color: rgba(var(--v-theme-deep), 0.35);
}
.house-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 56px;
  padding: 10px 16px;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
}
</style>
