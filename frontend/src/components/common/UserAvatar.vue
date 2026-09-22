<script setup lang="ts">
import { computed } from 'vue'
import type { UserShort } from '@/api/types'
import { fullName, initials } from '@/utils/format'

const props = withDefaults(defineProps<{ user: UserShort | null | undefined; size?: number }>(), {
  size: 40,
})

const COLORS = ['#03045E', '#023E8A', '#0077B6', '#0096C7', '#00B4D8', '#48CAE4']
const color = computed(() => COLORS[(props.user?.id ?? 0) % COLORS.length])
</script>

<template>
  <v-avatar :size="size" :color="user?.photo_url ? undefined : color" :title="fullName(user)">
    <v-img v-if="user?.photo_url" :src="user.photo_url" :alt="fullName(user)" cover />
    <span
      v-else
      class="font-semibold text-white"
      :style="{ fontSize: `${Math.round(size * 0.4)}px` }"
    >
      {{ initials(user) }}
    </span>
  </v-avatar>
</template>
