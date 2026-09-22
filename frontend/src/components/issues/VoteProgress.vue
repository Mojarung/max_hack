<script setup lang="ts">
import { gsap } from 'gsap'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { prefersReducedMotion } from '@/composables/useMotion'
import { plural } from '@/utils/format'

const props = withDefaults(
  defineProps<{ count: number; needed: number; compact?: boolean; done?: boolean }>(),
  { compact: false, done: false },
)

const bar = ref<HTMLElement | null>(null)
const ratio = computed(() =>
  props.done ? 1 : props.needed > 0 ? Math.min(1, props.count / props.needed) : 0,
)
let tween: gsap.core.Tween | null = null

watch(
  [ratio, bar],
  ([value, el], [prev]) => {
    if (!el) return
    tween?.kill()
    if (prefersReducedMotion()) {
      gsap.set(el, { scaleX: value })
      return
    }
    tween = gsap.fromTo(
      el,
      { scaleX: prev ?? 0 },
      { scaleX: value, duration: 0.9, ease: 'power3.out', transformOrigin: '0% 50%' },
    )
  },
  { immediate: true, flush: 'post' },
)
onBeforeUnmount(() => tween?.kill())
</script>

<template>
  <div>
    <div
      class="relative overflow-hidden rounded-full bg-on-surface/10"
      :class="compact ? 'h-2' : 'h-3'"
      role="progressbar"
      :aria-valuenow="count"
      :aria-valuemin="0"
      :aria-valuemax="needed"
      :aria-label="`Голосов: ${count} из ${needed}`"
    >
      <div
        ref="bar"
        class="absolute inset-0 origin-left rounded-full"
        :class="ratio >= 1 ? 'bg-success' : 'bg-primary'"
        style="transform: scaleX(0)"
      />
    </div>
    <div v-if="!compact" class="text-muted mt-1 flex justify-between text-sm">
      <span>
        <strong class="text-on-surface">{{ count }}</strong> из {{ needed }}
        {{ plural(needed, ['голоса', 'голосов', 'голосов']) }}
      </span>
      <span v-if="done || ratio >= 1" class="font-semibold text-success">Порог набран</span>
    </div>
  </div>
</template>
