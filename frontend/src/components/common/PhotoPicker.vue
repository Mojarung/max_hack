<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { notify } from '@/lib/notify'
import { haptic } from '@/max/bridge'
import { compressImage, MAX_PHOTOS } from '@/utils/image'

const files = defineModel<File[]>({ default: () => [] })
const props = withDefaults(defineProps<{ max?: number }>(), { max: MAX_PHOTOS })

const cameraInput = ref<HTMLInputElement | null>(null)
const galleryInput = ref<HTMLInputElement | null>(null)
const processing = ref(false)
const previews = ref<{ file: File; url: string }[]>([])
const left = computed(() => props.max - files.value.length)

watch(
  files,
  (list) => {
    const keep = previews.value.filter((p) => list.includes(p.file))
    previews.value.filter((p) => !list.includes(p.file)).forEach((p) => URL.revokeObjectURL(p.url))
    const added = list
      .filter((f) => !keep.some((p) => p.file === f))
      .map((file) => ({ file, url: URL.createObjectURL(file) }))
    previews.value = [...keep, ...added]
  },
  { immediate: true },
)

onBeforeUnmount(() => previews.value.forEach((p) => URL.revokeObjectURL(p.url)))

async function onPick(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const picked = Array.from(input.files ?? []).filter((f) => f.type.startsWith('image/'))
  input.value = ''
  if (picked.length === 0) return
  if (picked.length > left.value) notify.warning(`Можно добавить не больше ${props.max} фото`)
  processing.value = true
  try {
    const compressed = await Promise.all(
      picked.slice(0, Math.max(0, left.value)).map(compressImage),
    )
    files.value = [...files.value, ...compressed]
    haptic.impact('light')
  } finally {
    processing.value = false
  }
}

function remove(file: File): void {
  files.value = files.value.filter((f) => f !== file)
  haptic.selection()
}
</script>

<template>
  <div>
    <div class="flex gap-2">
      <v-btn
        class="flex-1"
        variant="tonal"
        color="primary"
        size="large"
        prepend-icon="mdi-camera"
        :disabled="left <= 0"
        :loading="processing"
        @click="cameraInput?.click()"
      >
        Камера
      </v-btn>
      <v-btn
        class="flex-1"
        variant="tonal"
        color="primary"
        size="large"
        prepend-icon="mdi-image-multiple"
        :disabled="left <= 0"
        :loading="processing"
        @click="galleryInput?.click()"
      >
        Галерея
      </v-btn>
    </div>
    <input
      ref="cameraInput"
      type="file"
      accept="image/*"
      capture="environment"
      class="sr-only"
      tabindex="-1"
      aria-hidden="true"
      @change="onPick"
    />
    <input
      ref="galleryInput"
      type="file"
      accept="image/jpeg,image/png,image/webp,image/*"
      multiple
      class="sr-only"
      tabindex="-1"
      aria-hidden="true"
      @change="onPick"
    />
    <div v-if="previews.length" class="mt-3 flex flex-wrap gap-2">
      <div
        v-for="(p, i) in previews"
        :key="p.url"
        class="relative h-[88px] w-[88px] overflow-hidden rounded-xl"
      >
        <img
          :src="p.url"
          :alt="`Фото ${i + 1}`"
          decoding="async"
          class="h-full w-full object-cover"
        />
        <v-btn
          icon="mdi-close"
          size="small"
          color="deep"
          class="!absolute top-1 right-1 opacity-80"
          :aria-label="`Убрать фото ${i + 1}`"
          @click="remove(p.file)"
        />
      </div>
    </div>
    <p class="text-muted mt-2 mb-0 text-sm">
      {{ files.length }} из {{ max }} фото. Сожмём перед отправкой, чтобы не тратить трафик.
    </p>
  </div>
</template>
