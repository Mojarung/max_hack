<script setup lang="ts">
import { gsap } from 'gsap'
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { prefersReducedMotion } from '@/composables/useMotion'
import { haptic } from '@/max/bridge'
import {
  FACES,
  armsMarkup,
  bootsMarkup,
  defsMarkup,
  dressMarkup,
  eyesMarkup,
  faceMarkup,
  fringeMarkup,
  hairBackMarkup,
  headMarkup,
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
  { mood: 'ok', size: 160, interactive: true, still: false },
)

const emit = defineEmits<{ tap: [] }>()

const uid = useId()
const ids: KuzyaIds = {
  dots: `kz-dots-${uid}`,
  felt: `kz-felt-${uid}`,
  skin: `kz-skin-${uid}`,
  glow: `kz-glow-${uid}`,
}

const face = computed(() => FACES[props.mood])
const glowColor = computed(() => (props.mood === 'alarm' ? '#00B4D8' : '#90E0EF'))
const label = computed(
  () =>
    ({
      happy: 'Домовой Кузя радуется',
      ok: 'Домовой Кузя спокоен',
      worried: 'Домовой Кузя удивлён',
      sad: 'Домовой Кузя грустит',
      alarm: 'Домовой Кузя бьёт тревогу',
      proud: 'Домовой Кузя гордится',
    })[props.mood],
)

// Разметка частей статична (без пользовательских данных), поэтому v-html безопасен.
const parts = computed(() => {
  const arms = armsMarkup(ids, face.value.pose)
  return {
    defs: defsMarkup(ids, glowColor.value),
    hair: hairBackMarkup(),
    boots: bootsMarkup(ids),
    dress: dressMarkup(ids),
    armLeft: arms.left,
    armRight: arms.right,
    armsFront: arms.front,
    head: headMarkup(ids),
    eyes: eyesMarkup(face.value),
    face: faceMarkup(face.value),
    fringe: fringeMarkup(),
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
  blinkCall?.kill()
  if (face.value.eyes.some((e) => e !== 'open')) return
  blinkCall = gsap.delayedCall(gsap.utils.random(2.2, 5.5), () => {
    if (!eyes.value) return
    gsap.to(eyes.value, {
      scaleY: 0.08,
      duration: 0.08,
      yoyo: true,
      repeat: 1,
      svgOrigin: '100 97',
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
        svgOrigin: '100 110',
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
    svgOrigin: '100 210',
    duration: 1.6,
    repeat: -1,
    yoyo: true,
    ease: 'sine.inOut',
  })
  // копна чуть покачивается, как пряжа
  gsap.to(hair.value, {
    rotation: 2,
    svgOrigin: '100 95',
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
      if (!props.still && !prefersReducedMotion()) scheduleBlink()
      if (!prefersReducedMotion() && figure.value) {
        gsap.fromTo(
          figure.value,
          { scale: 0.94 },
          { scale: 1, duration: 0.6, ease: 'elastic.out(1, 0.5)', svgOrigin: '100 210' },
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
        rotation: -110,
        duration: 0.2,
        svgOrigin: '124 128',
        ease: 'power2.out',
      })
      .to(armRight.value, {
        keyframes: [{ rotation: -90 }, { rotation: -120 }, { rotation: -90 }, { rotation: -115 }],
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
      <circle ref="glow" cx="100" cy="110" r="100" :fill="`url(#${ids.glow})`" opacity="0" />
      <ellipse cx="100" cy="210" rx="52" ry="6" fill="#03045E" opacity="0.14" />

      <g ref="figure">
        <g ref="hair" v-html="parts.hair" />
        <g v-html="parts.boots" />
        <g v-html="parts.dress" />
        <template v-if="!parts.armsFront">
          <g v-html="parts.armLeft" />
          <g ref="armRight" v-html="parts.armRight" />
        </template>
        <g v-html="parts.head" />
        <g ref="eyes" v-html="parts.eyes" />
        <g v-html="parts.face" />
        <g v-html="parts.fringe" />
        <template v-if="parts.armsFront">
          <g v-html="parts.armLeft" />
          <g ref="armRight" v-html="parts.armRight" />
        </template>
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
