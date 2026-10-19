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
  // «Проблемы» не влезает в пятую часть экрана 360px при шрифте 14px, а мельче нельзя
  { key: 'issues', to: '/issues', title: 'Заявки', icon: 'mdi-alert-circle-outline' },
  // Короткая подпись: «Барахолка» не помещается в пятую часть экрана 360px
  { key: 'market', to: '/market', title: 'Вещи', icon: 'mdi-storefront-outline' },
  { key: 'events', to: '/events', title: 'События', icon: 'mdi-calendar-star' },
  { key: 'more', to: '/more', title: 'Ещё', icon: 'mdi-dots-horizontal-circle-outline' },
]

const active = computed(() => route.meta.tab ?? 'home')
/** На внутренних экранах меню прячется: место под контент и кнопку действия, назад - кнопкой «Назад». */
const hidden = computed(() => !!route.meta.inner)
// Цифра на «Заявках» - то, что ждёт действия жителя: заявки, которые он ещё не поддержал.
// Проголосовал - цифра уменьшилась; открытые заявки дома без его участия её не держат
const awaiting = computed(() => pulse.pulse?.stats.awaiting_my_vote ?? 0)
</script>

<template>
  <nav
    class="bottom-nav"
    :class="{ 'bottom-nav--hidden': hidden }"
    :inert="hidden"
    aria-label="Разделы"
  >
    <div class="bottom-nav__inner glass">
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
            v-if="tab.key === 'issues' && awaiting > 0"
            :content="awaiting > 99 ? '99+' : awaiting"
            color="primary"
            floating
            :aria-label="`Ждут вашего голоса: ${awaiting}`"
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
/* Плавающая капсула над краем экрана, как таб-бар iOS 26 */
.bottom-nav {
  position: fixed;
  inset: auto 0 0 0;
  z-index: 1000;
  padding: 0 10px calc(var(--nav-gap) + env(safe-area-inset-bottom));
  pointer-events: none;
  transition:
    transform 0.42s var(--ease-spring),
    opacity 0.25s ease;
}
.bottom-nav--hidden {
  transform: translateY(calc(100% + 24px));
  opacity: 0;
  transition:
    transform 0.28s ease-in,
    opacity 0.2s ease;
}
.bottom-nav__inner {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  max-width: 520px;
  margin: 0 auto;
  height: var(--app-nav-height);
  padding: 5px;
  border-radius: 999px;
  pointer-events: auto;
}
.bottom-nav__item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  min-width: 0;
  border-radius: 999px;
  color: rgb(var(--v-theme-on-surface-variant));
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
  -webkit-tap-highlight-color: transparent;
  transition:
    background-color 0.25s ease,
    color 0.2s ease,
    transform 0.32s var(--ease-spring);
}
.bottom-nav__item:active {
  transform: scale(0.92);
  transition-duration: 0.1s;
}
.bottom-nav__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 30px;
}
.v-theme--dark .bottom-nav__item:not(.bottom-nav__item--active) {
  color: rgba(var(--v-theme-on-surface), 0.86);
}
/* Активная вкладка: «линза» под иконкой и подписью */
.bottom-nav__item--active {
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.13);
}
.v-theme--dark .bottom-nav__item--active {
  background: rgba(var(--v-theme-primary), 0.2);
}
.bottom-nav__item:focus-visible {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: -3px;
}
.bottom-nav__label {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.1;
}
</style>
