<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { haptic } from '@/max/bridge'
import type { TabKey } from '@/router'
import { usePulseStore } from '@/stores/pulse'

const route = useRoute()
const pulse = usePulseStore()

const tabs: { key: TabKey; to: string; title: string; icon: string }[] = [
  { key: 'home', to: '/', title: 'Дом', icon: 'mdi-home-heart' },
  { key: 'issues', to: '/issues', title: 'Проблемы', icon: 'mdi-alert-circle-outline' },
  { key: 'market', to: '/market', title: 'Барахолка', icon: 'mdi-storefront-outline' },
  { key: 'events', to: '/events', title: 'События', icon: 'mdi-calendar-star' },
  { key: 'more', to: '/more', title: 'Ещё', icon: 'mdi-dots-horizontal-circle-outline' },
]

const active = computed(() => route.meta.tab ?? 'home')
const openIssues = computed(() => pulse.pulse?.stats.open_issues ?? 0)
</script>

<template>
  <nav class="bottom-nav" aria-label="Разделы">
    <div class="bottom-nav__inner">
      <router-link
        v-for="tab in tabs"
        :key="tab.key"
        :to="tab.to"
        class="bottom-nav__item"
        :class="{ 'bottom-nav__item--active': active === tab.key }"
        :aria-current="active === tab.key ? 'page' : undefined"
        @click="haptic.selection()"
      >
        <span class="bottom-nav__icon">
          <v-badge
            v-if="tab.key === 'issues' && openIssues > 0"
            :content="openIssues > 99 ? '99+' : openIssues"
            color="error"
            floating
          >
            <v-icon :icon="tab.icon" size="26" />
          </v-badge>
          <v-icon v-else :icon="tab.icon" size="26" />
        </span>
        <span class="bottom-nav__label">{{ tab.title }}</span>
      </router-link>
    </div>
  </nav>
</template>

<style scoped>
.bottom-nav {
  position: fixed;
  inset: auto 0 0 0;
  z-index: 1000;
  padding-bottom: env(safe-area-inset-bottom);
  background: rgb(var(--v-theme-surface));
  border-top: 1px solid rgba(var(--v-border-color), 0.1);
}
.bottom-nav__inner {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  max-width: var(--app-max-width);
  margin: 0 auto;
  height: var(--app-nav-height);
}
.bottom-nav__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: rgba(var(--v-theme-on-surface), 0.62);
  text-decoration: none;
  font-size: 12px;
  font-weight: 600;
  -webkit-tap-highlight-color: transparent;
}
.bottom-nav__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 60px;
  height: 32px;
  border-radius: 16px;
  transition: background-color 0.2s ease;
}
.bottom-nav__item--active {
  color: rgb(var(--v-theme-primary));
}
.bottom-nav__item--active .bottom-nav__icon {
  background: rgba(var(--v-theme-primary), 0.14);
}
.bottom-nav__item:focus-visible {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: -3px;
  border-radius: 12px;
}
.bottom-nav__label {
  line-height: 1.1;
}
</style>
