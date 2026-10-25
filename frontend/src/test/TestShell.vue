<script setup lang="ts">
/**
 * Оболочка для тестов экранов: то же, что App.vue вокруг <router-view>,
 * но без загрузочного экрана, шапки и меню. Слой #fab-layer и тосты как в приложении.
 */
import { Toaster } from '@/components/ui/sonner'
</script>

<template>
  <v-app>
    <main>
      <router-view />
    </main>
    <div id="fab-layer" />
    <Toaster />
  </v-app>
</template>
