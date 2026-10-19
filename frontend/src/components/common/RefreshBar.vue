<script setup lang="ts">
/**
 * Тонкая полоса фоновой загрузки над списком. Место под неё занято всегда: появляясь и пропадая,
 * она не сдвигает список (иначе при смене вкладки экран подпрыгивает).
 */
defineProps<{ active: boolean }>()
</script>

<template>
  <div class="refresh-bar" :class="{ 'refresh-bar--on': active }" aria-hidden="true">
    <v-progress-linear v-if="active" indeterminate color="primary" height="3" rounded />
  </div>
</template>

<style scoped>
.refresh-bar {
  height: 3px;
  margin: 4px 0;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.refresh-bar--on {
  opacity: 1;
}
</style>
