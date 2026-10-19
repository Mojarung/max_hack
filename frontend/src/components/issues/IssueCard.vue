<script setup lang="ts">
import { computed, ref } from 'vue'
import type { IssueOut } from '@/api/types'
import StatusChip from './StatusChip.vue'
import VoteProgress from './VoteProgress.vue'
import { formatRelative, orgTitleCap, plural } from '@/utils/format'
import { ISSUE_STATUS_TITLES, issueCategoryIcon } from '@/utils/labels'

const props = defineProps<{ issue: IssueOut }>()

// Фото не загрузилось (файл удалён из хранилища) - показываем иконку категории, а не пустой квадрат
const broken = ref(false)
const cover = computed(() => (broken.value ? undefined : props.issue.photos[0]))
</script>

<template>
  <router-link
    :to="`/issues/${issue.id}`"
    class="card-soft tap-card flex gap-3 p-3 text-inherit no-underline"
    :class="{ 'issue-card--overdue': issue.is_overdue }"
    :aria-label="`${issue.title}. ${issue.is_overdue ? 'Просрочено' : ISSUE_STATUS_TITLES[issue.status]}`"
  >
    <div
      class="issue-thumb flex h-[76px] w-[76px] shrink-0 items-center justify-center overflow-hidden rounded-2xl"
      :class="{ 'issue-thumb--empty': !cover }"
    >
      <img
        v-if="cover"
        :src="cover"
        alt=""
        loading="lazy"
        class="h-full w-full object-cover"
        @error="broken = true"
      />
      <v-icon v-else :icon="issueCategoryIcon(issue.category)" size="34" color="primary" />
    </div>
    <div class="min-w-0 flex-1">
      <div class="mb-1">
        <StatusChip :status="issue.status" :overdue="issue.is_overdue" />
      </div>
      <h3 class="line-clamp-2 m-0 text-base leading-snug font-semibold">{{ issue.title }}</h3>
      <div v-if="issue.status === 'voting'" class="mt-2">
        <VoteProgress :count="issue.votes_count" :needed="issue.votes_needed" compact />
        <!-- категория всегда первой в нижней строке: не обрезается и не скачет между строками -->
        <div class="text-muted mt-1 text-sm">
          {{ issue.category_title }} · {{ issue.votes_count }} из {{ issue.votes_needed }}
          {{ plural(issue.votes_needed, ['голоса', 'голосов', 'голосов']) }}
          <span v-if="issue.voted_by_me" class="font-semibold text-success"> · вы поддержали</span>
        </div>
      </div>
      <div v-else class="text-muted mt-1 text-sm">
        {{ issue.category_title }} ·
        <span v-if="issue.responsible_org">{{ orgTitleCap(issue.responsible_org.name) }} · </span>
        <span class="whitespace-nowrap">{{ formatRelative(issue.created_at) }}</span>
      </div>
    </div>
  </router-link>
</template>

<style scoped>
/* Заявка без фото: мягкая плашка категории вместо серого квадрата, список не выглядит «дырявым» */
.issue-thumb--empty {
  background: linear-gradient(
    135deg,
    rgb(var(--v-theme-primary-container)),
    rgba(var(--v-theme-primary), 0.22)
  );
}

/* Просрочка видна в списке сразу: красная полоса слева, помимо чипа со статусом */
.issue-card--overdue {
  border-left: 4px solid rgb(var(--v-theme-deep));
}
</style>
