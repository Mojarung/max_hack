<script setup lang="ts">
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
</script>

<template>
  <main class="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
    <template v-if="session.status === 'error'">
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
