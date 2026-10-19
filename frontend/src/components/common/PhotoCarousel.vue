<script setup lang="ts">
import { computed, ref } from 'vue'

/**
 * Лента фото с перелистыванием: пальцем свайпом (нативная прокрутка со «щелчком» по кадру),
 * мышью перетаскиванием (composables/useDragScroll). Точки внизу показывают, какое фото открыто.
 * Высоту задаёт родитель: карусель занимает весь его блок. Фото, которые не загрузились, пропускаем;
 * если не загрузилось ни одно, показываем содержимое слота (иконку категории).
 */
// focusable: в галерее ленту листают и стрелками с клавиатуры; в карточке-ссылке фокус уже у ссылки
const props = defineProps<{ photos: string[]; alt: string; focusable?: boolean }>()
const emit = defineEmits<{ open: [index: number] }>()

const track = ref<HTMLElement | null>(null)
const current = ref(0)
const failed = ref<string[]>([])
const shown = computed(() => props.photos.filter((src) => !failed.value.includes(src)))

function onScroll(): void {
  const el = track.value
  if (!el || !el.clientWidth) return
  current.value = Math.min(shown.value.length - 1, Math.round(el.scrollLeft / el.clientWidth))
}

function go(index: number): void {
  const el = track.value
  if (!el) return
  el.scrollTo({ left: index * el.clientWidth, behavior: 'smooth' })
}
</script>

<template>
  <div v-if="!shown.length" class="flex h-full items-center justify-center">
    <slot />
  </div>
  <div v-else class="photo-carousel-wrap">
    <div
      ref="track"
      class="photo-carousel"
      :tabindex="focusable ? 0 : undefined"
      role="list"
      :aria-label="`Фото: ${alt}`"
      @scroll.passive="onScroll"
    >
      <div v-for="(src, i) in shown" :key="src" class="photo-carousel__slide" role="listitem">
        <img
          :src="src"
          :alt="`${alt}, фото ${i + 1} из ${shown.length}`"
          :loading="i === 0 ? 'eager' : 'lazy'"
          draggable="false"
          class="h-full w-full object-cover"
          @click="emit('open', props.photos.indexOf(src))"
          @error="failed = [...failed, src]"
        />
      </div>
    </div>
    <div v-if="shown.length > 1" class="photo-carousel__dots" aria-hidden="true">
      <span
        v-for="(src, i) in shown"
        :key="src"
        class="photo-carousel__dot"
        :class="{ 'photo-carousel__dot--on': i === current }"
        @click.stop.prevent="go(i)"
      />
    </div>
  </div>
</template>

<style scoped>
.photo-carousel-wrap {
  position: relative;
  height: 100%;
}
.photo-carousel {
  display: flex;
  height: 100%;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
}
.photo-carousel:focus-visible {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: -3px;
}
.photo-carousel::-webkit-scrollbar {
  display: none;
}
/* пока тянем мышью, «щелчок» по кадру отключён, иначе лента дёргается под курсором */
.photo-carousel.chips-scroll--dragging {
  scroll-snap-type: none;
  cursor: grabbing;
}
.photo-carousel__slide {
  flex: 0 0 100%;
  height: 100%;
  scroll-snap-align: start;
  scroll-snap-stop: always;
}
.photo-carousel__slide img {
  user-select: none;
}
.photo-carousel__dots {
  position: absolute;
  bottom: 8px;
  left: 50%;
  display: flex;
  gap: 5px;
  padding: 4px 7px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.32);
  transform: translateX(-50%);
}
.photo-carousel__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(var(--v-theme-light), 0.55);
  transition:
    width 0.25s var(--ease-spring),
    background 0.2s ease;
}
.photo-carousel__dot--on {
  width: 14px;
  border-radius: 999px;
  background: rgb(var(--v-theme-light));
}
@media (prefers-reduced-motion: reduce) {
  .photo-carousel__dot {
    transition: none;
  }
}
</style>
