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
    position="top-center"
    rich-colors
    close-button
    :duration="3500"
    :offset="{ top: 'calc(12px + env(safe-area-inset-top))' }"
    :toast-options="{ style: { fontSize: '15px', borderRadius: '16px' } }"
  />
</template>
