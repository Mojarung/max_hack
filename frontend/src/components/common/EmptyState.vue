<script setup lang="ts">
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import type { KuzyaMood } from '@/components/kuzya/mood'

withDefaults(defineProps<{ title: string; text?: string; mood?: KuzyaMood; size?: number }>(), {
  mood: 'ok',
  size: 120,
})
</script>

<template>
  <section class="flex flex-col items-center px-4 py-8 text-center" role="status">
    <KuzyaMascot :mood="mood" :size="size" quiet />
    <h3 class="mt-3 mb-1 text-lg font-bold">{{ title }}</h3>
    <p v-if="text" class="text-muted m-0 max-w-[320px]">{{ text }}</p>
    <div v-if="$slots.default" class="mt-4 flex flex-wrap justify-center gap-2">
      <slot />
    </div>
  </section>
</template>
