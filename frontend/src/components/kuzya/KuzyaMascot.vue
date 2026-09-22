<script setup lang="ts">
import { gsap } from 'gsap'
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { prefersReducedMotion } from '@/composables/useMotion'
import { haptic } from '@/max/bridge'
import { BODY_PATH, FACES, INK, PALETTES, ROOF, type KuzyaMood } from './geometry'

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
const bodyGradient = `kz-body-${uid}`
const glowGradient = `kz-glow-${uid}`

const palette = computed(() => PALETTES[props.mood])
const face = computed(() => FACES[props.mood])
const lanternColor = computed(() => (props.mood === 'alarm' ? '#FF3B30' : '#FFC94D'))
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

const root = ref<SVGSVGElement | null>(null)
const figure = ref<SVGGElement | null>(null)
const eyes = ref<SVGGElement | null>(null)
const armRight = ref<SVGGElement | null>(null)
const lantern = ref<SVGGElement | null>(null)
const glow = ref<SVGCircleElement | null>(null)
const smoke = ref<SVGGElement | null>(null)

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
      transformOrigin: '50% 55%',
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
      { opacity: 0.9, scale: 1 },
      {
        opacity: 0.15,
        scale: 1.35,
        duration: 0.35,
        repeat: -1,
        yoyo: true,
        transformOrigin: '50% 50%',
        ease: 'sine.inOut',
      },
    )
  } else {
    gsap.set(glow.value, { opacity: 0.45, scale: 1 })
  }
}

function startIdle(): void {
  if (!figure.value || !smoke.value || !lantern.value) return
  gsap.to(figure.value, {
    y: -4,
    scaleY: 1.025,
    scaleX: 0.99,
    transformOrigin: '50% 100%',
    duration: 1.5,
    repeat: -1,
    yoyo: true,
    ease: 'sine.inOut',
  })
  gsap.to(lantern.value, {
    rotation: 7,
    transformOrigin: '50% 0%',
    duration: 1.8,
    repeat: -1,
    yoyo: true,
    ease: 'sine.inOut',
  })
  const puffs = Array.from(smoke.value.children)
  puffs.forEach((puff, i) => {
    gsap
      .timeline({ repeat: -1, delay: i * 0.9 })
      .fromTo(
        puff,
        { y: 12, x: 0, scale: 0.3, opacity: 0, transformOrigin: '50% 50%' },
        { y: -8, x: 4, scale: 0.9, opacity: 0.85, duration: 1.2, ease: 'sine.out' },
      )
      .to(puff, { y: -30, x: 12, scale: 1.3, opacity: 0, duration: 1.5, ease: 'sine.in' })
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

/** Помахать лапкой по нажатию. */
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
        rotation: -70,
        duration: 0.18,
        transformOrigin: '20% 80%',
        ease: 'power2.out',
      })
      .to(armRight.value, {
        keyframes: [{ rotation: -40 }, { rotation: -75 }, { rotation: -40 }, { rotation: -70 }],
        duration: reduced ? 0.2 : 0.7,
        ease: 'sine.inOut',
      })
      .to(armRight.value, { rotation: 0, duration: 0.3, ease: 'back.out(2)' })
    if (!reduced) {
      gsap.fromTo(
        figure.value,
        { y: 0 },
        { y: -14, duration: 0.2, yoyo: true, repeat: 1, ease: 'power2.out' },
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
      <defs>
        <radialGradient :id="bodyGradient" cx="38%" cy="32%" r="75%">
          <stop offset="0%" :stop-color="palette.furLight" />
          <stop offset="70%" :stop-color="palette.fur" />
          <stop offset="100%" :stop-color="palette.furDark" />
        </radialGradient>
        <radialGradient :id="glowGradient">
          <stop offset="0%" :stop-color="lanternColor" stop-opacity="0.9" />
          <stop offset="100%" :stop-color="lanternColor" stop-opacity="0" />
        </radialGradient>
      </defs>

      <ellipse class="kz-shadow" cx="100" cy="206" rx="54" ry="8" fill="#000" opacity="0.12" />

      <g ref="figure">
        <!-- дым из трубы -->
        <g ref="smoke" fill="#CFC8C1">
          <circle cx="131" cy="30" r="6" opacity="0" />
          <circle cx="131" cy="30" r="8" opacity="0" />
          <circle cx="131" cy="30" r="7" opacity="0" />
        </g>

        <!-- ножки -->
        <ellipse cx="80" cy="192" rx="16" ry="9" :fill="palette.furDark" class="kz-fill" />
        <ellipse cx="120" cy="192" rx="16" ry="9" :fill="palette.furDark" class="kz-fill" />

        <!-- лапка с фонариком -->
        <g ref="lantern">
          <path d="M31 160 Q39 150 47 160" fill="none" stroke="#6D4C41" stroke-width="3" />
          <circle
            ref="glow"
            cx="39"
            cy="178"
            r="20"
            :fill="`url(#${glowGradient})`"
            opacity="0.45"
          />
          <rect x="28" y="162" width="22" height="28" rx="6" fill="#6D4C41" />
          <rect
            x="31.5"
            y="166"
            width="15"
            height="19"
            rx="4"
            :fill="lanternColor"
            class="kz-fill"
          />
          <rect x="30" y="188" width="18" height="5" rx="2.5" fill="#5D4037" />
        </g>

        <!-- тело -->
        <path :d="BODY_PATH" :fill="`url(#${bodyGradient})`" />
        <ellipse cx="100" cy="156" rx="34" ry="28" :fill="palette.belly" class="kz-fill" />

        <!-- левая лапка держит фонарик -->
        <ellipse
          cx="47"
          cy="150"
          rx="11"
          ry="16"
          transform="rotate(32 47 150)"
          :fill="palette.fur"
          class="kz-fill"
        />

        <!-- правая лапка (машет) -->
        <g ref="armRight">
          <ellipse
            cx="152"
            cy="146"
            rx="11"
            ry="16"
            transform="rotate(-28 152 146)"
            :fill="palette.fur"
            class="kz-fill"
          />
        </g>

        <!-- щёчки -->
        <ellipse cx="68" cy="140" rx="9" ry="6" :fill="palette.cheek" opacity="0.55" />
        <ellipse cx="132" cy="140" rx="9" ry="6" :fill="palette.cheek" opacity="0.55" />

        <!-- глаза -->
        <g ref="eyes">
          <ellipse cx="80" cy="123" rx="14" ry="16" fill="#fff" />
          <ellipse cx="120" cy="123" rx="14" ry="16" fill="#fff" />
          <g class="kz-pupils" :transform="`translate(${face.pupilDx} ${face.pupilDy})`">
            <circle cx="82" cy="126" r="8.5" :fill="INK" />
            <circle cx="122" cy="126" r="8.5" :fill="INK" />
            <circle cx="85" cy="122" r="3.2" fill="#fff" />
            <circle cx="125" cy="122" r="3.2" fill="#fff" />
            <circle cx="79" cy="130" r="1.4" fill="#fff" opacity="0.8" />
            <circle cx="119" cy="130" r="1.4" fill="#fff" opacity="0.8" />
          </g>
        </g>

        <!-- брови и рот -->
        <g fill="none" :stroke="INK" stroke-width="4" stroke-linecap="round">
          <path :d="face.browLeft" />
          <path :d="face.browRight" />
        </g>
        <path
          :d="face.mouth"
          :fill="face.mouthFilled ? '#6B2B1C' : 'none'"
          :stroke="INK"
          stroke-width="3.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <path
          v-if="mood === 'sad'"
          d="M68 136 Q64 144 68 148 Q72 144 68 136 Z"
          fill="#7EC8F2"
          opacity="0.9"
        />
        <path
          v-if="mood === 'alarm' || mood === 'worried'"
          d="M146 108 Q141 117 146 121 Q151 117 146 108 Z"
          fill="#7EC8F2"
          opacity="0.85"
        />

        <!-- шапка-крыша с трубой -->
        <g>
          <rect x="124" y="40" width="13" height="28" rx="2" :fill="ROOF.dark" />
          <rect x="121" y="36" width="19" height="7" rx="2.5" :fill="ROOF.dark" />
          <path
            d="M42 88 L100 36 L158 88 Z"
            :fill="ROOF.main"
            :stroke="ROOF.main"
            stroke-width="10"
            stroke-linejoin="round"
          />
          <path
            d="M44 90 L100 40 L156 90"
            fill="none"
            :stroke="ROOF.dark"
            stroke-width="4"
            stroke-linecap="round"
            stroke-linejoin="round"
            opacity="0.5"
          />
          <circle
            cx="100"
            cy="66"
            r="10"
            :fill="ROOF.window"
            :stroke="ROOF.dark"
            stroke-width="3"
          />
          <path d="M100 57 V75 M91 66 H109" :stroke="ROOF.dark" stroke-width="2.5" />
        </g>
      </g>
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
.kz-fill {
  transition: fill 0.4s ease;
}
</style>
