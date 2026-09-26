<script setup lang="ts">
import { computed } from 'vue'
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import { startBrowserDemo } from '@/api/mode'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()

/** Диплинк открывает мини-приложение из чата с Кузей: в приложении MAX или в web.max.ru. */
const maxLink = computed(() =>
  session.botUsername ? `https://max.ru/${session.botUsername}?startapp=home` : 'https://max.ru',
)

function openDemo(): void {
  if (!startBrowserDemo()) {
    notify.warning(
      'Браузер не дал включить демо',
      'Разрешите сохранение данных сайта или откройте Кузю в MAX',
    )
  }
}
</script>

<template>
  <main class="flex min-h-dvh flex-col items-center justify-center px-6 py-8 text-center">
    <template v-if="session.status === 'outside'">
      <KuzyaMascot mood="happy" :size="150" :interactive="false" />
      <h1 class="mt-4 mb-2 text-xl font-bold">Кузя живёт в MAX</h1>
      <p class="text-muted m-0 max-w-[360px]">
        Приложение открывается из чата с Кузей: так он узнаёт вас и ваш дом. Подойдёт MAX на
        телефоне или веб-версия на компьютере.
      </p>
      <div class="mt-6 flex w-full max-w-[360px] flex-col gap-3">
        <v-btn
          :href="maxLink"
          target="_blank"
          rel="noopener"
          color="primary"
          variant="flat"
          size="x-large"
          block
          prepend-icon="mdi-open-in-new"
        >
          Открыть в MAX
        </v-btn>
        <v-btn
          variant="tonal"
          size="large"
          block
          prepend-icon="mdi-play-circle-outline"
          @click="openDemo"
        >
          Посмотреть демо в браузере
        </v-btn>
      </div>
      <p class="text-muted mt-3 mb-0 max-w-[360px] text-sm">
        В демо вымышленный дом и соседи. Всё хранится только в этой вкладке, в настоящий чат и
        управляющую компанию ничего не уходит.
      </p>
    </template>
    <template v-else-if="session.status === 'error'">
      <KuzyaMascot mood="sad" :size="150" />
      <h1 class="mt-4 mb-2 text-xl font-bold">Кузя не смог открыть дверь</h1>
      <p class="text-muted m-0 max-w-[340px]" role="alert">{{ session.bootError }}</p>
      <v-btn
        class="mt-5"
        color="primary"
        size="large"
        prepend-icon="mdi-refresh"
        @click="session.init()"
      >
        Попробовать ещё раз
      </v-btn>
    </template>
    <template v-else>
      <KuzyaMascot mood="happy" :size="150" :interactive="false" />
      <p class="mt-4 mb-3 text-lg font-semibold" role="status">Кузя открывает дверь...</p>
      <v-progress-linear indeterminate color="primary" rounded class="max-w-[200px]" />
    </template>
  </main>
</template>
