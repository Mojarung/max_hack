<script setup lang="ts">
import { computed } from 'vue'
import type { IssueStatus } from '@/api/types'
import { ISSUE_STATUS_META, ISSUE_STATUS_TITLES } from '@/utils/labels'

const props = defineProps<{ status: IssueStatus; overdue?: boolean }>()
const meta = computed(() => ISSUE_STATUS_META[props.status] ?? ISSUE_STATUS_META.voting)
</script>

<template>
  <!-- Просрочка - самый тревожный статус: заливной тёмный, остальные спокойные тональные -->
  <v-chip
    :color="overdue ? 'deep' : meta.color"
    :variant="overdue ? 'flat' : 'tonal'"
    :prepend-icon="overdue ? 'mdi-clock-alert-outline' : meta.icon"
    class="font-semibold"
  >
    {{ overdue ? 'Просрочено' : ISSUE_STATUS_TITLES[status] }}
  </v-chip>
</template>
