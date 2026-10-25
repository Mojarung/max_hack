<script setup lang="ts">
import { gsap } from 'gsap'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { prefersReducedMotion } from '@/composables/useMotion'
import { haptic } from '@/max/bridge'
import { MOOD_LABELS, tapPose, type KuzyaMood } from './mood'
import { CANVAS, POSES } from './sprites'
import { preloadPose, spriteUrl } from './spriteUrl'

const props = withDefaults(
  defineProps<{
    mood?: KuzyaMood
    size?: number
    interactive?: boolean
    /** Без фоновых анимаций (для маленьких иконок в списках). */
    still?: boolean
    /** Смена настроения без прыжка: в пустых состояниях списков, где настроение меняют фильтры. */
    quiet?: boolean
  }>(),
  { mood: 'ok', size: 160, interactive: true, still: false, quiet: false },
)

const emit = defineEmits<{ tap: [] }>()

const height = computed(() => Math.round((props.size * CANVAS.height) / CANVAS.width))
const label = computed(() => MOOD_LABELS[props.mood])

const pct = (value: number, total: number) => `${((value / total) * 100).toFixed(2)}%`
const GROUND = `50% ${pct(CANVAS.ground, CANVAS.height)}`
const GROUND_BOTTOM = pct(CANVAS.height - CANVAS.ground, CANVAS.height)
/** Несколько Кузь на экране качаются вразнобой. */
const phase = `-${(Math.random() * 4).toFixed(2)}s`

/** Поза на экране: обычно совпадает с настроением, на нажатие ненадолго меняется. */
const pose = ref<KuzyaMood>(props.mood)
const layers = computed(() => {
  const meta = POSES[pose.value]
  return {
    body: spriteUrl(pose.value, 'body'),
    head: spriteUrl(pose.value, 'head'),
    lids: meta.blink ? spriteUrl(pose.value, 'lids') : undefined,
    neck: `${pct(meta.neck[0], CANVAS.width)} ${pct(meta.neck[1], CANVAS.height)}`,
  }
})

const reduced = ref(true)
const calm = computed(() => props.still || reduced.value)

const root = ref<HTMLElement | null>(null)
/** Разовые движения (прыжок, смена позы). Дыхание и покачивание головы живут в CSS. */
const bounce = ref<HTMLElement | null>(null)
const shadow = ref<HTMLElement | null>(null)

let ctx: gsap.Context | null = null
/** Первые данные о доме приходят сразу после появления: смену настроения тогда не анимируем. */
let mountedAt = 0
const SETTLE_MS = 1500
const TAP_POSE_SEC = 1.4
let blinkCall: gsap.core.Tween | null = null
let tapReturn: gsap.core.Tween | null = null
let switchToken = 0
/** Моргание перезапускает само себя из колбэков: после размонтирования цепочку надо оборвать. */
let disposed = false

function currentLids(): HTMLElement | null {
  return (
    root.value?.querySelector<HTMLElement>('.kuzya__pose:not(.kz-pose-leave-active) [data-lids]') ??
    null
  )
}

function scheduleBlink(): void {
  blinkCall?.kill()
  if (disposed || calm.value || !layers.value.lids) return
  blinkCall = gsap.delayedCall(gsap.utils.random(2.8, 6), () => {
    const lids = currentLids()
    if (!lids) return scheduleBlink()
    const tl = gsap.timeline({ onComplete: scheduleBlink })
    // иногда моргает дважды подряд, так живее
    const times = Math.random() < 0.2 ? 2 : 1
    for (let i = 0; i < times; i++) {
      // веки опускаются и поднимаются плавно: резкое мигание читается как дёрганье
      tl.to(lids, { opacity: 1, duration: 0.1, ease: 'sine.inOut', delay: i ? 0.18 : 0 }).to(lids, {
        opacity: 0,
        duration: 0.16,
        ease: 'sine.inOut',
        delay: 0.08,
      })
    }
  })
}

/** Мягко осесть и выпрямиться после смены позы. */
function squash(): void {
  if (calm.value || !bounce.value) return
  gsap.fromTo(
    bounce.value,
    { scaleX: 1.025, scaleY: 0.965 },
    {
      scaleX: 1,
      scaleY: 1,
      duration: 0.55,
      ease: 'back.out(1.3)',
      transformOrigin: GROUND,
      overwrite: 'auto',
    },
  )
}

async function switchPose(next: KuzyaMood, animate: boolean): Promise<void> {
  const token = ++switchToken
  await preloadPose(next)
  if (token !== switchToken || next === pose.value) return
  pose.value = next
  ctx?.add(() => {
    if (animate) squash()
    scheduleBlink()
  })
}

/** Один плавный прыжок: присел, взлетел по дуге, мягко приземлился. */
function hop(): void {
  if (calm.value || !bounce.value || !shadow.value) return
  gsap.killTweensOf([bounce.value, shadow.value])
  gsap
    .timeline({ defaults: { transformOrigin: GROUND } })
    .to(bounce.value, { scaleX: 1.03, scaleY: 0.95, yPercent: 0, duration: 0.16, ease: 'sine.in' })
    .to(bounce.value, {
      scaleX: 0.985,
      scaleY: 1.025,
      yPercent: -11,
      duration: 0.3,
      ease: 'power2.out',
    })
    .to(shadow.value, { scale: 0.78, opacity: 0.6, duration: 0.3, ease: 'power2.out' }, '<')
    .to(bounce.value, { scaleX: 1, scaleY: 1, yPercent: 0, duration: 0.28, ease: 'power2.in' })
    .to(shadow.value, { scale: 1, opacity: 1, duration: 0.28, ease: 'power2.in' }, '<')
    .to(bounce.value, { scaleX: 1.025, scaleY: 0.97, duration: 0.12, ease: 'sine.out' })
    .to(bounce.value, { scaleX: 1, scaleY: 1, duration: 0.45, ease: 'back.out(1.2)' })
}

/** По нажатию Кузя подпрыгивает и на секунду радуется (если в доме всё спокойно). */
function greet(): void {
  if (!props.interactive) return
  haptic.impact('light')
  emit('tap')
  ctx?.add(() => {
    hop()
    const next = tapPose(props.mood)
    if (!next) return
    tapReturn?.kill()
    void switchPose(next, false)
    tapReturn = gsap.delayedCall(TAP_POSE_SEC, () => void switchPose(props.mood, true))
  })
}

onMounted(() => {
  mountedAt = performance.now()
  reduced.value = prefersReducedMotion()
  ctx = gsap.context(() => scheduleBlink(), root.value ?? undefined)
})

watch(
  () => props.mood,
  (mood) => {
    tapReturn?.kill()
    void switchPose(mood, !props.quiet && performance.now() - mountedAt > SETTLE_MS)
  },
)

onBeforeUnmount(() => {
  disposed = true
  switchToken++
  blinkCall?.kill()
  tapReturn?.kill()
  ctx?.revert()
})
</script>

<template>
  <component
    :is="interactive ? 'button' : 'span'"
    ref="root"
    class="kuzya"
    :class="[`kuzya--${pose}`, { 'kuzya--calm': calm, 'kuzya--alarm': mood === 'alarm' }]"
    :type="interactive ? 'button' : undefined"
    :role="interactive ? undefined : 'img'"
    :aria-label="interactive ? `${label}. Нажмите, чтобы поздороваться` : label"
    :style="{
      width: `${size}px`,
      height: `${height}px`,
      '--kz-phase': phase,
      '--kz-ground': GROUND,
      '--kz-ground-bottom': GROUND_BOTTOM,
    }"
    @click="greet"
  >
    <span class="kuzya__glow" aria-hidden="true" />
    <span ref="shadow" class="kuzya__shadow" aria-hidden="true" />
    <span ref="bounce" class="kuzya__stage" aria-hidden="true">
      <span class="kuzya__figure">
        <Transition name="kz-pose" :css="!calm">
          <span :key="pose" class="kuzya__pose">
            <img :src="layers.body" class="kuzya__layer" alt="" draggable="false" />
            <span class="kuzya__head" :style="{ transformOrigin: layers.neck }">
              <img :src="layers.head" class="kuzya__layer" alt="" draggable="false" />
              <img
                v-if="layers.lids"
                :src="layers.lids"
                class="kuzya__layer kuzya__lids"
                data-lids
                alt=""
                draggable="false"
              />
            </span>
          </span>
        </Transition>
      </span>
    </span>
  </component>
</template>

<style scoped>
.kuzya {
  /*
   * Характер движения по настроению: амплитуда и темп покачивания головы и дыхания.
   * Циклы не короче 2,4 с и амплитуда до 2°: быстрее и шире читается как дёрганье.
   */
  --kz-sway: 1.3deg;
  --kz-tilt: 0deg;
  --kz-sway-time: 5.6s;
  --kz-breath: 1.014;
  --kz-breath-time: 4.2s;
  /* синусоида: без ускорений на концах хода */
  --kz-ease: cubic-bezier(0.37, 0, 0.63, 1);
  position: relative;
  display: inline-block;
  flex-shrink: 0;
  padding: 0;
  margin: 0;
  border: 0;
  background: none;
  cursor: default;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}
.kuzya--happy {
  --kz-sway: 2deg;
  --kz-sway-time: 3.6s;
  --kz-breath: 1.02;
  --kz-breath-time: 2.8s;
}
.kuzya--proud {
  --kz-tilt: 1.5deg;
  --kz-sway-time: 4.8s;
}
.kuzya--sad {
  --kz-sway: 0.9deg;
  --kz-tilt: -2.5deg;
  --kz-sway-time: 7s;
  --kz-breath: 1.011;
  --kz-breath-time: 5.2s;
}
.kuzya--alarm {
  --kz-sway: 1deg;
  --kz-sway-time: 2.4s;
  --kz-breath: 1.018;
  --kz-breath-time: 2.4s;
}
.kuzya--worried {
  --kz-sway: 1.1deg;
  --kz-sway-time: 4s;
}
button.kuzya {
  cursor: pointer;
  border-radius: var(--r-lg);
}
button.kuzya:focus-visible {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: 4px;
}

.kuzya__stage,
.kuzya__figure,
.kuzya__pose,
.kuzya__head,
.kuzya__layer {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.kuzya__layer {
  display: block;
  pointer-events: none;
  -webkit-user-drag: none;
}
.kuzya__lids {
  opacity: 0;
}

.kuzya__shadow {
  position: absolute;
  left: 24%;
  right: 24%;
  bottom: calc(var(--kz-ground-bottom) - 3%);
  height: 6%;
  border-radius: 50%;
  background: radial-gradient(closest-side, rgba(var(--v-theme-on-surface), 0.2), transparent);
}
.kuzya__glow {
  position: absolute;
  inset: -10% -14%;
  border-radius: 50%;
  background: radial-gradient(closest-side, rgba(var(--v-theme-error), 0.4), transparent);
  opacity: 0;
}
.kuzya--alarm .kuzya__glow {
  opacity: 0.6;
}

.kuzya:not(.kuzya--calm) .kuzya__figure {
  transform-origin: var(--kz-ground);
  animation: kz-breathe var(--kz-breath-time) var(--kz-ease) var(--kz-phase) infinite;
  will-change: transform;
}
.kuzya:not(.kuzya--calm) .kuzya__head {
  animation: kz-sway var(--kz-sway-time) var(--kz-ease) var(--kz-phase) infinite alternate;
  will-change: transform;
}
/* растровые слои под трансформацией: без мерцания краёв при масштабе и повороте */
.kuzya__figure,
.kuzya__head,
.kuzya__layer {
  backface-visibility: hidden;
}
.kuzya--calm .kuzya__head {
  transform: rotate(var(--kz-tilt));
}
.kuzya--alarm:not(.kuzya--calm) .kuzya__glow {
  animation: kz-alarm 1.6s var(--kz-ease) infinite alternate;
}

/* смена позы: новая проявляется, старая тает под ней одновременно, без пустого кадра */
.kuzya__pose {
  z-index: 1;
}
.kz-pose-enter-active {
  transition: opacity 0.26s ease-out;
}
.kz-pose-enter-from {
  opacity: 0;
}
.kz-pose-leave-active {
  z-index: 0;
  transition: opacity 0.26s ease-in;
}
.kz-pose-leave-to {
  opacity: 0;
}

@keyframes kz-breathe {
  0%,
  100% {
    transform: scale(1, 1);
  }
  50% {
    transform: scale(calc(2 - var(--kz-breath)), var(--kz-breath));
  }
}
/* голова только качается, без подскоков по вертикали */
@keyframes kz-sway {
  from {
    transform: rotate(calc(var(--kz-tilt) - var(--kz-sway)));
  }
  to {
    transform: rotate(calc(var(--kz-tilt) + var(--kz-sway)));
  }
}
@keyframes kz-alarm {
  from {
    opacity: 0.75;
    transform: scale(1);
  }
  to {
    opacity: 0.35;
    transform: scale(1.08);
  }
}
</style>
