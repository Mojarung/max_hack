<script setup lang="ts">
import { Skeleton } from '@/components/ui/skeleton'

withDefaults(defineProps<{ count?: number; variant?: 'row' | 'grid' }>(), {
  count: 4,
  variant: 'row',
})
</script>

<template>
  <div
    :class="variant === 'grid' ? 'grid grid-cols-2 gap-3' : 'flex flex-col gap-3'"
    aria-busy="true"
    aria-label="Загрузка"
  >
    <template v-if="variant === 'grid'">
      <div v-for="i in count" :key="i" class="card-soft overflow-hidden">
        <Skeleton class="h-[130px] rounded-none" />
        <div class="p-3">
          <Skeleton class="mb-2 h-4 w-3/4" />
          <Skeleton class="h-4 w-1/3" />
        </div>
      </div>
    </template>
    <template v-else>
      <div v-for="i in count" :key="i" class="card-soft flex gap-3 p-3">
        <Skeleton class="h-[72px] w-[72px] shrink-0" />
        <div class="flex-1">
          <Skeleton class="mb-2 h-4 w-4/5" />
          <Skeleton class="mb-3 h-3 w-1/2" />
          <Skeleton class="h-2 w-full" />
        </div>
      </div>
    </template>
  </div>
</template>
