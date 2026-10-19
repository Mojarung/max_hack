<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { UserShort } from '@/api/types'
import { defaultPreset, presetAvatar } from '@/utils/avatar'
import { fullName, initials } from '@/utils/format'

const props = withDefaults(defineProps<{ user: UserShort | null | undefined; size?: number }>(), {
  size: 40,
})

/** Фото из MAX или выбранная картинка; у жителя без фото - войлочный шарик по его id. */
const src = computed(() => {
  if (!props.user) return null
  return props.user.photo_url || presetAvatar(defaultPreset(props.user.id))
})
// Картинка не загрузилась (нет сети, битая ссылка): показываем инициалы
const failed = ref(false)
watch(src, () => (failed.value = false))

/** Шесть спокойных цветов темы для инициалов; текст (on-*) проходит WCAG AA в обеих темах. */
const COLORS = ['primary', 'secondary', 'tertiary', 'success', 'warning', 'ink'] as const
const color = computed(() => COLORS[(props.user?.id ?? 0) % COLORS.length])
/** В маленьком аватаре две буквы стали бы мельче 14px: оставляем одну. */
const letters = computed(() => {
  const text = initials(props.user)
  return props.size < 36 ? text.slice(0, 1) : text
})
const fontSize = computed(() => Math.max(14, Math.round(props.size * 0.4)))
const showImage = computed(() => !!src.value && !failed.value)
</script>

<template>
  <v-avatar :size="size" :color="showImage ? undefined : color" :title="fullName(user)">
    <v-img v-if="showImage" :src="src!" :alt="fullName(user)" cover @error="failed = true" />
    <span v-else class="font-semibold" :style="{ fontSize: `${fontSize}px` }" aria-hidden="true">
      {{ letters }}
    </span>
  </v-avatar>
</template>
