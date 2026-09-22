<script setup lang="ts">
import { computed } from 'vue'
import type { IssueStatus } from '@/api/types'
import { ISSUE_STATUS_META } from '@/utils/labels'

const props = defineProps<{ status: IssueStatus; title: string; overdue?: boolean }>()
const meta = computed(() => ISSUE_STATUS_META[props.status] ?? ISSUE_STATUS_META.voting)
</script>

<template>
  <v-chip
    :color="overdue ? 'error' : meta.color"
    size="small"
    variant="tonal"
    :prepend-icon="overdue ? 'mdi-clock-alert-outline' : meta.icon"
    class="font-semibold"
  >
    {{ overdue ? 'Просрочено' : title }}
  </v-chip>
</template>
