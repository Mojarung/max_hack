<script setup lang="ts">
import { gsap } from 'gsap'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AnimatedNumber from './AnimatedNumber.vue'
import { prefersReducedMotion } from '@/composables/useMotion'
import { scoreColor } from '@/utils/labels'

const props = withDefaults(defineProps<{ score: number; size?: number }>(), { size: 112 })

const R = 44
const C = 2 * Math.PI * R
const arc = ref<SVGCircleElement | null>(null)
const color = computed(() => `rgb(var(--v-theme-${scoreColor(props.score)}))`)
const clamped = computed(() => Math.max(0, Math.min(100, props.score)))
let tween: gsap.core.Tween | null = null

watch(
  [clamped, arc],
  ([score, el]) => {
    if (!el) return
    tween?.kill()
    const offset = C * (1 - score / 100)
    if (prefersReducedMotion()) gsap.set(el, { strokeDashoffset: offset })
    else tween = gsap.to(el, { strokeDashoffset: offset, duration: 1.2, ease: 'power3.out' })
  },
  { immediate: true, flush: 'post' },
)
onBeforeUnmount(() => tween?.kill())
</script>

<template>
  <div
    class="relative inline-flex items-center justify-center"
    :style="{ width: `${size}px`, height: `${size}px` }"
    role="img"
    :aria-label="`Здоровье дома ${clamped} из 100`"
  >
    <svg :width="size" :height="size" viewBox="0 0 100 100" class="-rotate-90">
      <circle
        cx="50"
        cy="50"
        :r="R"
        fill="none"
        stroke="currentColor"
        stroke-opacity="0.1"
        stroke-width="9"
      />
      <circle
        ref="arc"
        cx="50"
        cy="50"
        :r="R"
        fill="none"
        :stroke="color"
        stroke-width="9"
        stroke-linecap="round"
        :stroke-dasharray="C"
        :stroke-dashoffset="C"
      />
    </svg>
    <div class="absolute inset-0 flex flex-col items-center justify-center leading-none">
      <strong class="text-[28px]"><AnimatedNumber :value="clamped" /></strong>
      <span class="text-muted mt-1 text-[11px]">из 100</span>
    </div>
  </div>
</template>
