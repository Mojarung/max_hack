<script setup lang="ts">
import { DrawerDescription, DrawerTitle } from 'vaul-vue'

defineProps<{ title: string; description?: string }>()
</script>

<template>
  <header class="pt-2 pb-3">
    <DrawerTitle class="m-0 text-xl font-bold">{{ title }}</DrawerTitle>
    <DrawerDescription v-if="description" class="mt-1 mb-0 text-sm text-muted">
      {{ description }}
    </DrawerDescription>
  </header>
</template>
