<script setup lang="ts">
import { gsap } from 'gsap'
import { onBeforeUnmount, ref, watch } from 'vue'
import { prefersReducedMotion } from '@/composables/useMotion'

const props = withDefaults(defineProps<{ value: number; duration?: number }>(), { duration: 0.9 })

const shown = ref(0)
const state = { v: 0 }
let tween: gsap.core.Tween | null = null

watch(
  () => props.value,
  (target) => {
    tween?.kill()
    if (prefersReducedMotion()) {
      state.v = target
      shown.value = target
      return
    }
    tween = gsap.to(state, {
      v: target,
      duration: props.duration,
      ease: 'power2.out',
      onUpdate: () => (shown.value = Math.round(state.v)),
    })
  },
  { immediate: true },
)

onBeforeUnmount(() => tween?.kill())
</script>

<template>
  <span class="tabular-nums">{{ shown }}</span>
</template>
