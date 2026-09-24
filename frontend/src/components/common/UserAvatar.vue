<script setup lang="ts">
import { computed } from 'vue'
import type { UserShort } from '@/api/types'
import { fullName, initials } from '@/utils/format'

const props = withDefaults(defineProps<{ user: UserShort | null | undefined; size?: number }>(), {
  size: 40,
})

/** Цвета темы, у которых текст (on-*) проходит WCAG AA в обеих темах. */
const COLORS = ['deep', 'primary'] as const
const color = computed(() => COLORS[(props.user?.id ?? 0) % COLORS.length])
/** В маленьком аватаре две буквы стали бы мельче 14px: оставляем одну. */
const letters = computed(() => {
  const text = initials(props.user)
  return props.size < 36 ? text.slice(0, 1) : text
})
const fontSize = computed(() => Math.max(14, Math.round(props.size * 0.4)))
</script>

<template>
  <v-avatar :size="size" :color="user?.photo_url ? undefined : color" :title="fullName(user)">
    <v-img v-if="user?.photo_url" :src="user.photo_url" :alt="fullName(user)" cover />
    <span v-else class="font-semibold" :style="{ fontSize: `${fontSize}px` }" aria-hidden="true">
      {{ letters }}
    </span>
  </v-avatar>
</template>
