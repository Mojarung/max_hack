<script setup lang="ts" generic="T extends string">
import { computed, ref } from 'vue'
import { prefersReducedMotion } from '@/composables/useMotion'
import { useSwipeTabs } from '@/composables/useSwipeTabs'
import { haptic } from '@/max/bridge'

/**
 * Сегментированный переключатель как в iOS: капсула и «бегунок» под выбранным пунктом.
 * Семантика radiogroup: диктор читает «выбрано», стрелки переключают пункт.
 */
const props = defineProps<{
  options: { value: T; label: string; icon?: string }[]
  label: string
}>()
const model = defineModel<T>({ required: true })

const index = computed(() =>
  Math.max(
    0,
    props.options.findIndex((o) => o.value === model.value),
  ),
)

const root = ref<HTMLElement | null>(null)
// Высота шапки со «стеклом»: переключатель должен остаться виден под ней
const HEADER_OFFSET = 72
// Плавная прокрутка к переключателю занимает около полсекунды
const SCROLL_HOLD_MS = 800

function pick(value: T): void {
  if (value === model.value) return
  haptic.selection()
  // направление для анимации списка: следующая вкладка въезжает справа, предыдущая слева
  const next = props.options.findIndex((o) => o.value === value)
  const area = root.value?.parentElement?.querySelector<HTMLElement>('.list-area')
  if (area) area.dataset.dir = next > index.value ? 'next' : 'prev'
  model.value = value
  // Переключатель ушёл под шапку (список пролистан): плавно возвращаемся к нему, иначе короткий
  // новый список обрезает прокрутку и экран дёргается
  const top = root.value?.getBoundingClientRect().top ?? 0
  if (top < HEADER_OFFSET) {
    // пока едем вверх, список не должен укоротиться: держим высоту области, потом отпускаем
    if (area) {
      area.style.minHeight = `${area.offsetHeight}px`
      window.setTimeout(() => (area.style.minHeight = ''), SCROLL_HOLD_MS)
    }
    window.scrollBy({
      top: top - HEADER_OFFSET - 8,
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    })
  }
}

// Свайп по экрану под переключателем листает вкладки; на краях дальше не идёт
useSwipeTabs(
  () => root.value?.parentElement,
  (step) => {
    const next = props.options[index.value + step]
    if (next) pick(next.value)
  },
)

function onKey(event: KeyboardEvent): void {
  const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
  if (!step) return
  event.preventDefault()
  const next = props.options[(index.value + step + props.options.length) % props.options.length]
  if (next) pick(next.value)
}
</script>

<template>
  <div
    ref="root"
    class="segmented"
    role="radiogroup"
    :aria-label="label"
    :style="{ '--count': options.length, '--index': index }"
    @keydown="onKey"
  >
    <span class="segmented__thumb" aria-hidden="true" />
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      role="radio"
      class="segmented__item"
      :class="{ 'segmented__item--active': o.value === model }"
      :aria-checked="o.value === model"
      :tabindex="o.value === model ? 0 : -1"
      @click="pick(o.value)"
    >
      <v-icon v-if="o.icon" :icon="o.icon" size="20" aria-hidden="true" />
      <span class="segmented__label">{{ o.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.segmented {
  position: relative;
  display: grid;
  grid-template-columns: repeat(var(--count), minmax(0, 1fr));
  height: 48px;
  padding: 4px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.07);
}
.v-theme--dark .segmented {
  background: rgba(var(--v-theme-on-surface), 0.1);
}
.segmented__thumb {
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 4px;
  width: calc((100% - 8px) / var(--count));
  border-radius: 999px;
  background: rgb(var(--v-theme-surface));
  box-shadow:
    0 1px 2px rgba(16, 24, 40, 0.08),
    0 4px 12px -4px rgba(16, 24, 40, 0.18);
  transform: translateX(calc(100% * var(--index)));
  transition: transform 0.38s var(--ease-spring);
}
.v-theme--dark .segmented__thumb {
  background: rgb(var(--v-theme-surface-bright));
}
.segmented__item {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 0;
  padding: 0 8px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  font: inherit;
  font-size: 1rem;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), var(--muted-alpha));
  -webkit-tap-highlight-color: transparent;
  transition: color 0.2s ease;
}
.segmented__item--active {
  color: rgb(var(--v-theme-on-surface));
}
.segmented__item:focus-visible {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.segmented__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
