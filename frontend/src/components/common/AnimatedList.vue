<script setup lang="ts">
import { computed } from 'vue'
import { prefersReducedMotion } from '@/composables/useMotion'

/**
 * Список, который плавно перестраивается при смене фильтра: оставшиеся карточки доезжают
 * на новое место, ушедшие растворяются там, где стояли. Появление новых делает useReveal.
 */
withDefaults(defineProps<{ tag?: string }>(), { tag: 'div' })

const animated = computed(() => !prefersReducedMotion())

// Уходящий элемент снимаем с потока на его же месте, иначе соседи не смогут подъехать
function beforeLeave(el: Element): void {
  const node = el as HTMLElement
  const { offsetTop, offsetLeft, offsetWidth, offsetHeight } = node
  Object.assign(node.style, {
    position: 'absolute',
    top: `${offsetTop}px`,
    left: `${offsetLeft}px`,
    width: `${offsetWidth}px`,
    height: `${offsetHeight}px`,
  })
}
</script>

<template>
  <TransitionGroup
    :tag="tag"
    name="alist"
    :css="animated"
    class="alist"
    @before-leave="animated ? beforeLeave($event) : undefined"
  >
    <slot />
  </TransitionGroup>
</template>

<style>
.alist {
  position: relative;
}
.alist-move {
  transition: transform 0.45s var(--ease-spring);
}
.alist-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
  pointer-events: none;
  z-index: 0;
}
.alist-leave-to {
  opacity: 0;
  transform: scale(0.96);
}
</style>
