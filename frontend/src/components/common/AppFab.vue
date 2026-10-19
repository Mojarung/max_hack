<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * Плавающая кнопка «создать» над навигацией.
 * Рисуется в отдельном слое (#fab-layer), а не внутри страницы: страница въезжает с анимацией,
 * и кнопка с position: fixed внутри неё ехала бы вместе со страницей и вставала на место с опозданием.
 * При прокрутке вниз сворачивается в круг с иконкой и не закрывает список, при прокрутке вверх
 * снова показывает подпись.
 */
defineOptions({ inheritAttrs: false })
defineProps<{ icon: string; label: string; ariaLabel?: string }>()

// Сдвиг прокрутки, после которого меняем вид: мелкое дрожание пальца не мигает подписью
const SCROLL_STEP_PX = 12
// У самого верха экрана подпись видна всегда
const TOP_ZONE_PX = 80

const compact = ref(false)
let lastY = 0

function onScroll(): void {
  const y = window.scrollY
  if (Math.abs(y - lastY) < SCROLL_STEP_PX) return
  compact.value = y > TOP_ZONE_PX && y > lastY
  lastY = y
}

onMounted(() => {
  lastY = window.scrollY
  window.addEventListener('scroll', onScroll, { passive: true })
})
onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))
</script>

<template>
  <Teleport defer to="#fab-layer">
    <Transition name="fab-pop" appear>
      <v-btn
        color="primary"
        size="large"
        rounded="xl"
        class="fab"
        :class="{ 'fab--compact': compact }"
        :aria-label="ariaLabel ?? label"
        v-bind="$attrs"
      >
        <v-icon :icon="icon" size="24" aria-hidden="true" />
        <span class="fab__label">{{ label }}</span>
      </v-btn>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fab {
  padding-inline: 18px;
  transition:
    padding 0.28s var(--ease-spring),
    min-width 0.28s var(--ease-spring);
}
.fab__label {
  display: inline-block;
  max-width: 14em;
  margin-left: 8px;
  overflow: hidden;
  white-space: nowrap;
  transition:
    max-width 0.28s var(--ease-spring),
    margin 0.28s var(--ease-spring),
    opacity 0.18s ease;
}
.fab--compact {
  min-width: 56px !important;
  padding-inline: 16px;
}
.fab--compact .fab__label {
  max-width: 0;
  margin-left: 0;
  opacity: 0;
}
.fab-pop-enter-active {
  transition:
    opacity 0.22s ease,
    transform 0.32s var(--ease-spring);
}
.fab-pop-enter-from {
  opacity: 0;
  transform: translateY(12px) scale(0.92);
}
@media (prefers-reduced-motion: reduce) {
  .fab,
  .fab__label,
  .fab-pop-enter-active {
    transition: none;
  }
}
</style>
