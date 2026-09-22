<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: HTMLAttributes['class'] }>()
</script>

<template>
  <div aria-hidden="true" :class="cn('skeleton rounded-xl bg-on-surface/[0.08]', props.class)" />
</template>

<style scoped>
.skeleton {
  position: relative;
  overflow: hidden;
}
.skeleton::after {
  content: '';
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, rgba(202, 240, 248, 0.45), transparent);
  animation: skeleton-shimmer 1.4s infinite;
}
@keyframes skeleton-shimmer {
  to {
    transform: translateX(100%);
  }
}
</style>
