<script setup lang="ts">
import { stopBrowserDemo } from '@/api/mode'
</script>

<template>
  <div class="demo-bar" role="note">
    <div class="demo-bar__inner">
      <v-icon icon="mdi-information-outline" size="20" color="primary" aria-hidden="true" />
      <span class="demo-bar__text">Демо: дом и соседи вымышленные</span>
      <v-btn variant="text" color="primary" size="large" class="shrink-0" @click="stopBrowserDemo">
        Выйти
      </v-btn>
    </div>
  </div>
</template>

<style scoped>
.demo-bar {
  background: rgb(var(--v-theme-surface));
  border-bottom: 1px solid rgba(var(--v-border-color), 0.08);
}
.demo-bar__inner {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: var(--app-max-width);
  margin: 0 auto;
  padding: 0 4px 0 16px;
}
.demo-bar__text {
  flex: 1;
  min-width: 0;
  font-size: 0.875rem;
  line-height: 1.3;
}
</style>
