<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ photos: string[]; alt: string; height?: number }>()

const open = ref(false)
const index = ref(0)

function show(i: number): void {
  index.value = i
  open.value = true
}
</script>

<template>
  <div v-if="photos.length" class="gallery">
    <div class="chips-scroll !gap-2 !pb-1" role="list" :aria-label="`Фото: ${alt}`">
      <button
        v-for="(src, i) in photos"
        :key="src"
        type="button"
        role="listitem"
        class="gallery__item tap-card shrink-0 overflow-hidden rounded-2xl border-0 bg-surface-variant p-0"
        :class="photos.length === 1 ? 'w-full' : 'w-[82%]'"
        :style="{ height: `${height ?? 240}px` }"
        :aria-label="`Открыть фото ${i + 1} из ${photos.length}`"
        @click="show(i)"
      >
        <img
          :src="src"
          :alt="`${alt}, фото ${i + 1}`"
          class="h-full w-full object-cover"
          loading="lazy"
        />
      </button>
    </div>

    <v-dialog v-model="open" fullscreen transition="fade-transition">
      <div class="relative flex h-full flex-col bg-black">
        <v-btn
          icon="mdi-close"
          variant="text"
          color="light"
          class="!absolute top-3 right-3 z-10"
          aria-label="Закрыть фото"
          @click="open = false"
        />
        <v-carousel
          v-model="index"
          height="100%"
          :show-arrows="photos.length > 1 ? 'hover' : false"
          :hide-delimiters="photos.length < 2"
          :continuous="false"
        >
          <v-carousel-item v-for="(src, i) in photos" :key="src">
            <v-img :src="src" :alt="`${alt}, фото ${i + 1}`" contain height="100%" />
          </v-carousel-item>
        </v-carousel>
      </div>
    </v-dialog>
  </div>
</template>

<style scoped>
.gallery__item {
  scroll-snap-align: start;
}
</style>
