<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import DemoUserSwitcher from './DemoUserSwitcher.vue'
import { realtimeStatus } from '@/realtime/sse'
import { goBack } from '@/router'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const session = useSessionStore()
const inner = computed(() => !!route.meta.inner)
const title = computed(() =>
  route.name === 'home' ? (session.me?.house.title ?? 'Домовой Кузя') : route.meta.title,
)
</script>

<template>
  <header class="app-header">
    <div class="app-header__inner">
      <v-btn
        v-if="inner"
        icon="mdi-arrow-left"
        variant="text"
        size="large"
        aria-label="Назад"
        @click="goBack"
      />
      <router-link
        v-else
        to="/"
        class="flex h-12 w-12 shrink-0 items-center justify-center"
        aria-label="На главную"
      >
        <img src="/kuzya.svg" alt="" width="36" height="40" />
      </router-link>
      <h1 class="app-header__title">{{ title }}</h1>
      <v-chip
        v-if="realtimeStatus === 'reconnecting'"
        size="small"
        color="warning"
        variant="tonal"
        prepend-icon="mdi-wifi-off"
        class="shrink-0"
      >
        Нет связи
      </v-chip>
      <DemoUserSwitcher
        v-if="!session.inMax && session.devUsers.length && route.name !== 'dev-chat'"
        class="shrink-0"
      />
    </div>
  </header>
</template>

<style scoped>
.app-header {
  position: sticky;
  top: 0;
  z-index: 1000;
  padding-top: env(safe-area-inset-top);
  background: rgb(var(--v-theme-background));
  border-bottom: 1px solid rgba(var(--v-border-color), 0.08);
}
.app-header__inner {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: var(--app-max-width);
  margin: 0 auto;
  min-height: 60px;
  padding: 0 12px 0 6px;
}
.app-header__title {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: 1.125rem;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
