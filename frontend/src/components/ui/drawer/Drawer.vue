<script setup lang="ts">
import { DrawerRoot } from 'vaul-vue'

defineProps<{ dismissible?: boolean }>()
const open = defineModel<boolean>('open', { default: false })
</script>

<template>
  <DrawerRoot v-model:open="open" :dismissible="dismissible ?? true" should-scale-background>
    <slot />
  </DrawerRoot>
</template>
