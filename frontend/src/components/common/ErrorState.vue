<script setup lang="ts">
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'

withDefaults(defineProps<{ message: string; title?: string; retrying?: boolean }>(), {
  title: 'Не получилось загрузить',
})
defineEmits<{ retry: [] }>()
</script>

<template>
  <section class="flex flex-col items-center px-4 py-8 text-center" role="alert">
    <KuzyaMascot mood="sad" :size="110" />
    <h3 class="mt-3 mb-1 text-lg font-bold">{{ title }}</h3>
    <p class="text-muted m-0 max-w-[320px]">{{ message }}</p>
    <v-btn
      class="mt-4"
      color="primary"
      size="large"
      prepend-icon="mdi-refresh"
      :loading="retrying"
      @click="$emit('retry')"
    >
      Попробовать ещё раз
    </v-btn>
  </section>
</template>
