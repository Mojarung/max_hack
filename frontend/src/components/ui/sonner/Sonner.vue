<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from 'vuetify'
import { Toaster } from 'vue-sonner'
import 'vue-sonner/style.css'

const theme = useTheme()
const mode = computed(() => (theme.current.value.dark ? 'dark' : 'light'))
</script>

<template>
  <Toaster
    :theme="mode"
    position="bottom-center"
    close-button
    :duration="3500"
    :offset="{ bottom: 'calc(var(--app-nav-height) + 12px + env(safe-area-inset-bottom))' }"
    :toast-options="{
      style: {
        fontSize: '15px',
        borderRadius: '16px',
        color: 'rgb(var(--v-theme-on-surface))',
        background: 'rgb(var(--v-theme-surface))',
        border: '1px solid rgba(var(--v-theme-primary), 0.3)',
      },
    }"
  />
</template>
