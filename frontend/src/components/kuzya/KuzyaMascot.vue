<script setup lang="ts">
import { gsap } from 'gsap'
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { prefersReducedMotion } from '@/composables/useMotion'
import { haptic } from '@/max/bridge'
import {
  FACES,
  PALETTES,
  armLeftMarkup,
  armRightMarkup,
  bootsMarkup,
  chestMarkup,
  defsMarkup,
  eyesMarkup,
  faceMarkup,
  fringeMarkup,
  hairBackMarkup,
  headMarkup,
  shirtMarkup,
  type KuzyaIds,
  type KuzyaMood,
} from './geometry'

const props = withDefaults(
  defineProps<{
    mood?: KuzyaMood
    size?: number
    interactive?: boolean
    /** Без фоновых анимаций (для маленьких иконок в списках). */
    still?: boolean
  }>(),
  { mood: 'happy', size: 160, interactive: true, still: false },
)

const emit = defineEmits<{ tap: [] }>()

const uid = useId()
const ids: KuzyaIds = {
  dots: `kz-dots-${uid}`,
  knit: `kz-knit-${uid}`,
  skin: `kz-skin-${uid}`,
  glow: `kz-glow-${uid}`,
}

const palette = computed(() => PALETTES[props.mood])
const face = computed(() => FACES[props.mood])
const glowColor = computed(() => (props.mood === 'alarm' ? '#00B4D8' : '#90E0EF'))
const label = computed(
  () =>
    ({
      happy: 'Домовой Кузя радуется',
      ok: 'Домовой Кузя спокоен',
      worried: 'Домовой Кузя волнуется',
      sad: 'Домовой Кузя грустит',
      alarm: 'Домовой Кузя бьёт тревогу',
    })[props.mood],
)

// Разметка частей статична (без пользовательских данных), поэтому v-html безопасен.
const parts = computed(() => {
  const p = palette.value
  return {
    defs: defsMarkup(ids, p, glowColor.value),
    hair: hairBackMarkup(p),
    chest: chestMarkup(),
    boots: bootsMarkup(ids),
    shirt: shirtMarkup(ids, p),
    armLeft: armLeftMarkup(ids, p),
    armRight: armRightMarkup(ids, p),
    head: headMarkup(ids, p),
    fringe: fringeMarkup(p),
    eyes: eyesMarkup(face.value),
    face: faceMarkup(face.value, p, props.mood),
  }
})

const root = ref<SVGSVGElement | null>(null)
const figure = ref<SVGGElement | null>(null)
const hair = ref<SVGGElement | null>(null)
const eyes = ref<SVGGElement | null>(null)
const armRight = ref<SVGGElement | null>(null)
const glow = ref<SVGCircleElement | null>(null)

let ctx: gsap.Context | null = null
let alarmTween: gsap.core.Tween | null = null
let blinkCall: gsap.core.Tween | null = null

function scheduleBlink(): void {
  blinkCall = gsap.delayedCall(gsap.utils.random(2.2, 5.5), () => {
    if (!eyes.value) return
    gsap.to(eyes.value, {
      scaleY: 0.08,
      duration: 0.08,
      yoyo: true,
      repeat: 1,
      transformOrigin: '50% 50%',
      ease: 'power1.inOut',
      onComplete: scheduleBlink,
    })
  })
}

function startAlarm(): void {
  alarmTween?.kill()
  alarmTween = null
  if (!glow.value) return
  if (props.mood === 'alarm') {
    alarmTween = gsap.fromTo(
      glow.value,
      { opacity: 0.85, scale: 1 },
      {
        opacity: 0.2,
        scale: 1.15,
        duration: 0.35,
        repeat: -1,
        yoyo: true,
        transformOrigin: '50% 50%',
        ease: 'sine.inOut',
      },
    )
  } else {
    gsap.set(glow.value, { opacity: 0, scale: 1 })
  }
}

function startIdle(): void {
  if (!figure.value || !hair.value) return
  gsap.to(figure.value, {
    y: -3,
    scaleY: 1.02,
    scaleX: 0.99,
    transformOrigin: '50% 100%',
    duration: 1.6,
    repeat: -1,
    yoyo: true,
    ease: 'sine.inOut',
  })
  // шевелюра чуть покачивается, как пряжа
  gsap.to(hair.value, {
    rotation: 2.5,
    transformOrigin: '50% 90%',
    duration: 2.2,
    repeat: -1,
    yoyo: true,
    ease: 'sine.inOut',
  })
  scheduleBlink()
}

onMounted(() => {
  ctx = gsap.context(() => {
    startAlarm()
    if (!props.still && !prefersReducedMotion()) startIdle()
  }, root.value ?? undefined)
})

watch(
  () => props.mood,
  () => {
    ctx?.add(() => {
      startAlarm()
      if (!prefersReducedMotion() && figure.value) {
        gsap.fromTo(
          figure.value,
          { scale: 0.94 },
          { scale: 1, duration: 0.6, ease: 'elastic.out(1, 0.5)', transformOrigin: '50% 100%' },
        )
      }
    })
  },
)

onBeforeUnmount(() => {
  blinkCall?.kill()
  alarmTween?.kill()
  ctx?.revert()
})

/** Помахать рукой по нажатию. */
function wave(): void {
  if (!props.interactive) return
  haptic.impact('light')
  emit('tap')
  if (!armRight.value || !figure.value) return
  ctx?.add(() => {
    const reduced = prefersReducedMotion()
    gsap
      .timeline()
      .to(armRight.value, {
        rotation: -115,
        duration: 0.2,
        transformOrigin: '8% 6%',
        ease: 'power2.out',
      })
      .to(armRight.value, {
        keyframes: [{ rotation: -95 }, { rotation: -125 }, { rotation: -95 }, { rotation: -120 }],
        duration: reduced ? 0.2 : 0.8,
        ease: 'sine.inOut',
      })
      .to(armRight.value, { rotation: 0, duration: 0.35, ease: 'back.out(2)' })
    if (!reduced) {
      gsap.fromTo(
        figure.value,
        { y: 0 },
        { y: -12, duration: 0.2, yoyo: true, repeat: 1, ease: 'power2.out' },
      )
    }
  })
}
</script>

<template>
  <component
    :is="interactive ? 'button' : 'span'"
    class="kuzya"
    :type="interactive ? 'button' : undefined"
    :aria-label="interactive ? `${label}. Нажмите, чтобы помахать` : undefined"
    :style="{ width: `${size}px`, height: `${Math.round(size * 1.1)}px` }"
    @click="wave"
  >
    <svg
      ref="root"
      viewBox="0 0 200 220"
      :width="size"
      :height="Math.round(size * 1.1)"
      role="img"
      :aria-label="label"
      focusable="false"
    >
      <!-- eslint-disable vue/no-v-html -- статичная разметка маскота из geometry.ts -->
      <defs v-html="parts.defs" />
      <circle ref="glow" cx="100" cy="120" r="96" :fill="`url(#${ids.glow})`" opacity="0" />
      <ellipse cx="100" cy="209" rx="62" ry="7" fill="#03045E" opacity="0.14" />

      <g ref="figure">
        <g ref="hair" v-html="parts.hair" />
        <g v-html="parts.chest" />
        <g v-html="parts.boots" />
        <g v-html="parts.shirt" />
        <g v-html="parts.armLeft" />
        <g ref="armRight" v-html="parts.armRight" />
        <g v-html="parts.head" />
        <g v-html="parts.fringe" />
        <g ref="eyes" v-html="parts.eyes" />
        <g v-html="parts.face" />
      </g>
      <!-- eslint-enable vue/no-v-html -->
    </svg>
  </component>
</template>

<style scoped>
.kuzya {
  display: inline-flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0;
  margin: 0;
  border: 0;
  background: none;
  cursor: default;
  -webkit-tap-highlight-color: transparent;
}
button.kuzya {
  cursor: pointer;
  border-radius: 24px;
}
button.kuzya:focus-visible {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: 4px;
}
svg {
  overflow: visible;
}
</style>
