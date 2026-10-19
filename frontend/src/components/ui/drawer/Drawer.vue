<script setup lang="ts">
import { DrawerRoot } from 'vaul-vue'

// Отсутствующий boolean-проп Vue превращает в false, поэтому значение по умолчанию задаём явно:
// без него шторку нельзя было смахнуть вниз.
const props = withDefaults(defineProps<{ dismissible?: boolean }>(), { dismissible: true })
const open = defineModel<boolean>('open', { default: false })
</script>

<template>
  <DrawerRoot v-model:open="open" :dismissible="props.dismissible" should-scale-background>
    <slot />
  </DrawerRoot>
</template>
