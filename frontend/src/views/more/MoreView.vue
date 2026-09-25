<script setup lang="ts">
import { computed, ref } from 'vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import HouseSwitcher from '@/components/house/HouseSwitcher.vue'
import { useStagger } from '@/composables/useMotion'
import { openMaxLink } from '@/max/bridge'
import { useSessionStore } from '@/stores/session'
import { fullName } from '@/utils/format'

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
      subtitle: 'Адрес, управляющая компания, контакты',
      icon: 'mdi-home-city-outline',
      color: 'primary',
    },
    {
      to: '/announcements',
      title: 'Объявления',
      subtitle: 'Отключения, работы, собрания',
      icon: 'mdi-bullhorn-variant-outline',
      color: 'primary',
    },
    {
      to: '/more/documents',
      title: 'Документы',
      subtitle: 'Документы дома и ваши личные',
      icon: 'mdi-file-document-multiple-outline',
      color: 'primary',
    },
    {
      to: '/people',
      title: 'Соседи',
      subtitle: 'Профили жителей дома',
      icon: 'mdi-account-group-outline',
      color: 'primary',
    },
    {
      to: '/more/safety',
      title: 'Безопасность',
      subtitle: 'Укрытия рядом и что делать при тревоге',
      icon: 'mdi-shield-home-outline',
      color: 'error',
    },
    {
      to: '/more/search',
      title: 'Поиск',
      subtitle: 'По проблемам, событиям и барахолке',
      icon: 'mdi-magnify',
      color: 'info',
    },
    {
      to: '/more/assistant',
      title: 'Спросить Кузю',
      subtitle: 'Ответит здесь: заявки, сроки, события',
      icon: 'mdi-chat-processing-outline',
      color: 'primary',
    },
    {
      to: '/more/achievements',
      title: 'Награды и рейтинг',
      subtitle: 'Награды за добрые дела',
      icon: 'mdi-trophy-outline',
      color: 'warning',
    },
  ]
  if (session.canUseDevTools) {
    list.push({
      to: '/dev/chat',
      title: 'Эмулятор чата MAX',
      subtitle: 'Демо сценариев бота без MAX',
      icon: 'mdi-message-cog-outline',
      color: 'secondary',
    })
  }
  if (session.canManageMcp) {
    list.push({
      to: '/more/mcp',
      title: 'Настройки MCP',
      subtitle: 'Инструменты для ИИ-помощника',
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
    <router-link
      v-if="session.me"
      :to="`/people/${session.me.user.id}`"
      class="card-soft tap-card flex items-center gap-3 p-4 text-inherit no-underline"
      aria-label="Мой профиль"
      data-stagger
    >
      <UserAvatar :user="session.me.user" :size="56" />
      <div class="min-w-0 flex-1">
        <div class="text-lg font-bold">{{ fullName(session.me.user) }}</div>
        <div class="text-muted text-sm">
          <template v-if="session.me.user.apartment"
            >Квартира {{ session.me.user.apartment }} ·
          </template>
          {{ session.me.user.level_title }}
        </div>
        <div class="text-muted text-sm">{{ session.me.house.title }}</div>
      </div>
      <v-chip color="primary" variant="tonal" prepend-icon="mdi-star-circle-outline">
        {{ session.me.user.points }}
      </v-chip>
    </router-link>

    <HouseSwitcher v-if="session.houses.length">
      <template #trigger="{ open }">
        <v-btn
          block
          size="large"
          variant="tonal"
          color="primary"
          class="mt-3"
          prepend-icon="mdi-home-switch-outline"
          data-stagger
          @click="open"
        >
          {{ session.houses.length > 1 ? `Сменить дом (${session.houses.length})` : 'Мои дома' }}
        </v-btn>
      </template>
    </HouseSwitcher>

    <nav class="mt-3 flex flex-col gap-2" aria-label="Разделы">
      <router-link
        v-for="e in entries"
        :key="e.to"
        :to="e.to"
        class="card-soft tap-card flex items-center gap-3 p-3 text-inherit no-underline"
        data-stagger
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
