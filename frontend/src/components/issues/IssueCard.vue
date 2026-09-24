<script setup lang="ts">
import type { IssueOut } from '@/api/types'
import StatusChip from './StatusChip.vue'
import VoteProgress from './VoteProgress.vue'
import { formatRelative, plural } from '@/utils/format'
import { ISSUE_STATUS_TITLES, issueCategoryIcon } from '@/utils/labels'

defineProps<{ issue: IssueOut }>()
</script>

<template>
  <router-link
    :to="`/issues/${issue.id}`"
    class="card-soft tap-card flex gap-3 p-3 text-inherit no-underline"
    :aria-label="`${issue.title}. ${issue.is_overdue ? 'Просрочено' : ISSUE_STATUS_TITLES[issue.status]}`"
  >
    <div
      class="flex h-[76px] w-[76px] shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-surface-variant"
    >
      <img
        v-if="issue.photos[0]"
        :src="issue.photos[0]"
        alt=""
        loading="lazy"
        class="h-full w-full object-cover"
      />
      <v-icon v-else :icon="issueCategoryIcon(issue.category)" size="34" color="primary" />
    </div>
    <div class="min-w-0 flex-1">
      <div class="mb-1 flex flex-wrap items-center gap-1.5">
        <StatusChip :status="issue.status" :overdue="issue.is_overdue" />
        <span class="text-muted text-sm">{{ issue.category_title }}</span>
      </div>
      <h3 class="line-clamp-2 m-0 text-base leading-snug font-semibold">{{ issue.title }}</h3>
      <div v-if="issue.status === 'voting'" class="mt-2">
        <VoteProgress :count="issue.votes_count" :needed="issue.votes_needed" compact />
        <div class="text-muted mt-1 text-sm">
          {{ issue.votes_count }} из {{ issue.votes_needed }}
          {{ plural(issue.votes_needed, ['голоса', 'голосов', 'голосов']) }}
          <span v-if="issue.voted_by_me" class="font-semibold text-primary"> · вы поддержали</span>
        </div>
      </div>
      <div v-else class="text-muted mt-1 text-sm">
        <span v-if="issue.responsible_org">{{ issue.responsible_org.name }} · </span>
        <span class="whitespace-nowrap">{{ formatRelative(issue.created_at) }}</span>
      </div>
    </div>
  </router-link>
</template>
