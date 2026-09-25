<script setup lang="ts">
import { DrawerContent, DrawerOverlay, DrawerPortal } from 'vaul-vue'
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: HTMLAttributes['class'] }>()
</script>

<template>
  <DrawerPortal to=".v-application">
    <DrawerOverlay class="fixed inset-0 z-[2400] bg-black/60" />
    <DrawerContent
      :class="
        cn(
          'fixed inset-x-0 bottom-0 z-[2401] mx-auto flex max-h-[92dvh] w-full max-w-[640px] flex-col rounded-t-[24px] bg-surface text-on-surface outline-none',
          'pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_40px_-12px_rgba(16,24,40,0.35)]',
          props.class,
        )
      "
    >
      <div
        class="mx-auto mt-3 mb-1 h-1.5 w-12 shrink-0 rounded-full bg-on-surface/20"
        aria-hidden="true"
      />
      <div class="overflow-y-auto px-4 pb-4">
        <slot />
      </div>
    </DrawerContent>
  </DrawerPortal>
</template>
