<script setup lang="ts">
import type { AnnouncementOut } from '@/api/types'
import { formatRelative, fullName } from '@/utils/format'

defineProps<{ item: AnnouncementOut; clamp?: boolean }>()
</script>

<template>
  <article class="card-soft announcement p-4" :class="{ 'announcement--pinned': item.pinned }">
    <div class="flex items-start gap-3">
      <v-icon
        :icon="item.pinned ? 'mdi-pin' : 'mdi-bullhorn-variant-outline'"
        color="primary"
        size="24"
        class="mt-0.5 shrink-0"
        aria-hidden="true"
      />
      <div class="min-w-0 flex-1">
        <h3 class="m-0 text-base leading-snug font-bold">
          <span v-if="item.pinned" class="sr-only">Закреплено. </span>{{ item.title }}
        </h3>
        <p v-if="item.text" class="announcement__text m-0 mt-1" :class="{ 'line-clamp-3': clamp }">
          {{ item.text }}
        </p>
        <div class="text-muted mt-2 text-sm">
          <template v-if="item.author">{{ fullName(item.author) }} · </template>
          {{ formatRelative(item.created_at) }}
          <template v-if="item.pinned"> · закреплено</template>
        </div>
        <router-link
          v-if="item.event_id"
          :to="`/events/${item.event_id}`"
          class="announcement__link"
        >
          Записаться на событие <v-icon icon="mdi-chevron-right" size="20" />
        </router-link>
        <slot />
      </div>
    </div>
  </article>
</template>

<style scoped>
.announcement--pinned {
  border-color: rgba(var(--v-theme-primary), 0.45);
}
.announcement__text {
  white-space: pre-line;
  line-height: 1.45;
}
.announcement__link {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  margin-bottom: -8px;
  font-weight: 700;
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}
</style>
