<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import DemoUserSwitcher from './DemoUserSwitcher.vue'
import HouseSwitcher from '@/components/house/HouseSwitcher.vue'
import { realtimeStatus } from '@/realtime/sse'
import { goBack } from '@/router'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const session = useSessionStore()
const inner = computed(() => !!route.meta.inner)
/** На главной название дома - кнопка выбора дома, если домов несколько. */
const showSwitcher = computed(() => route.name === 'home' && session.houses.length > 1)
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
        <img src="/kuzya-head.png" alt="" width="40" height="40" />
      </router-link>
      <h1 v-if="showSwitcher" class="app-header__title flex"><HouseSwitcher /></h1>
      <h1 v-else class="app-header__title">{{ title }}</h1>
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
/* Шапка из «стекла»: контент мягко уходит под неё при прокрутке */
.app-header {
  position: sticky;
  top: 0;
  z-index: 1000;
  padding-top: env(safe-area-inset-top);
  background: rgba(var(--v-theme-background), 0.78);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid rgba(var(--v-border-color), 0.06);
}
@media (prefers-reduced-transparency: reduce) {
  .app-header {
    background: rgb(var(--v-theme-background));
    -webkit-backdrop-filter: none;
    backdrop-filter: none;
  }
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
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
