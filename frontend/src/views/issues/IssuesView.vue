<script setup lang="ts">
import AppFab from '@/components/common/AppFab.vue'
import { watchDebounced } from '@vueuse/core'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { IssueStatus } from '@/api/types'
import AnimatedList from '@/components/common/AnimatedList.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import RefreshBar from '@/components/common/RefreshBar.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import IssueCard from '@/components/issues/IssueCard.vue'
import { useStagger } from '@/composables/useMotion'
import { haptic } from '@/max/bridge'
import { useIssuesStore } from '@/stores/issues'
import { usePulseStore } from '@/stores/pulse'
import { useSessionStore } from '@/stores/session'
import { plural } from '@/utils/format'
import { ISSUE_STATUSES } from '@/utils/labels'

const store = useIssuesStore()
const pulse = usePulseStore()
const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const list = ref<HTMLElement | null>(null)
const search = ref(store.query)

/** «Просрочено» - не статус сервера, а признак: фильтруем на месте, живёт в адресе (?overdue=1). */
const overdueOnly = computed(() => route.query.overdue === '1')
/** «Ждут вашего голоса» - тоже фильтр на месте (?vote=1): голосование, не поддержанное, не своё. */
const voteOnly = computed(() => route.query.vote === '1')
const special = computed(() => overdueOnly.value || voteOnly.value)
const awaiting = computed(() => pulse.pulse?.stats.awaiting_my_vote ?? 0)
const items = computed(() => {
  if (overdueOnly.value) return store.items.filter((i) => i.is_overdue)
  if (voteOnly.value)
    return store.items.filter(
      (i) => i.status === 'voting' && !i.voted_by_me && i.author?.id !== session.me?.user.id,
    )
  return store.items
})
const showSkeleton = computed(() => store.loading && !store.loaded)
const isFiltered = computed(() => !!store.status || !!store.query.trim() || special.value)
const showFab = computed(() => !(store.loaded && items.value.length === 0 && !isFiltered.value))

useStagger(list, () => items.value.length)

function setOverdue(on: boolean): void {
  haptic.selection()
  if (on) store.status = null
  void router.replace({ query: on ? { overdue: '1' } : {} })
}

function setVoteOnly(on: boolean): void {
  haptic.selection()
  store.status = on ? 'voting' : null
  void router.replace({ query: on ? { vote: '1' } : {} })
}

const chips = ref<HTMLElement | null>(null)

onMounted(() => {
  void store.load()
  // Выбранный фильтр мог оказаться за краем ряда (например, пришли по ссылке «Просрочено»)
  void nextTick(() =>
    chips.value
      ?.querySelector('[aria-pressed="true"]')
      ?.scrollIntoView({ inline: 'center', block: 'nearest' }),
  )
})

function setStatus(value: IssueStatus | null): void {
  if (special.value) void router.replace({ query: {} })
  if (store.status === value) return
  haptic.selection()
  store.status = value
}

watch(
  () => store.status,
  () => void store.load(),
)
watchDebounced(
  search,
  (value) => {
    store.query = value ?? ''
    void store.load()
  },
  { debounce: 400 },
)
</script>

<template>
  <div class="page page--with-fab">
    <v-text-field
      v-model="search"
      placeholder="Поиск по заявкам"
      prepend-inner-icon="mdi-magnify"
      clearable
      density="comfortable"
      aria-label="Поиск по заявкам"
      class="mb-2"
    />

    <div ref="chips" class="chips-scroll" role="toolbar" aria-label="Фильтр по статусу">
      <v-chip
        v-for="s in ISSUE_STATUSES.slice(0, 2)"
        :key="s.title"
        :color="!special && store.status === s.value ? 'primary' : undefined"
        :variant="!special && store.status === s.value ? 'flat' : 'outlined'"
        size="large"
        class="filter-chip"
        role="button"
        :aria-pressed="!special && store.status === s.value"
        @click="setStatus(s.value)"
      >
        {{ s.title }}
      </v-chip>
      <v-chip
        :color="overdueOnly ? 'deep' : undefined"
        :variant="overdueOnly ? 'flat' : 'outlined'"
        size="large"
        class="filter-chip"
        role="button"
        prepend-icon="mdi-clock-alert-outline"
        :aria-pressed="overdueOnly"
        @click="setOverdue(!overdueOnly)"
      >
        Просрочено
      </v-chip>
      <v-chip
        v-for="s in ISSUE_STATUSES.slice(2)"
        :key="s.title"
        :color="!special && store.status === s.value ? 'primary' : undefined"
        :variant="!special && store.status === s.value ? 'flat' : 'outlined'"
        size="large"
        class="filter-chip"
        role="button"
        :aria-pressed="!special && store.status === s.value"
        @click="setStatus(s.value)"
      >
        {{ s.title }}
      </v-chip>
    </div>

    <!-- Откуда цифра на вкладке: заявки, которые ждут голоса этого жителя. Одно нажатие - и они перед глазами -->
    <button
      v-if="awaiting > 0 || voteOnly"
      type="button"
      class="vote-hint tap-card mt-2"
      :class="{ 'vote-hint--on': voteOnly }"
      :aria-pressed="voteOnly"
      @click="setVoteOnly(!voteOnly)"
    >
      <v-icon icon="mdi-hand-back-right-outline" size="24" aria-hidden="true" />
      <span class="min-w-0 flex-1 text-left">
        <template v-if="!voteOnly">
          <b
            >{{ awaiting }} {{ plural(awaiting, ['заявка ждёт', 'заявки ждут', 'заявок ждут']) }}</b
          >
          вашего голоса
        </template>
        <template v-else>Только заявки, которые ждут вашего голоса</template>
      </span>
      <span class="vote-hint__action">{{ voteOnly ? 'Показать все' : 'Показать' }}</span>
    </button>

    <RefreshBar :active="store.loading && store.loaded" />

    <div class="list-area mt-1">
      <Transition name="swap" mode="out-in">
        <ListSkeleton v-if="showSkeleton" />
        <ErrorState
          v-else-if="store.error && items.length === 0"
          :message="store.error"
          :retrying="store.loading"
          @retry="store.load()"
        />
        <EmptyState
          v-else-if="store.loaded && items.length === 0"
          :mood="isFiltered && !voteOnly ? 'ok' : 'happy'"
          :title="
            voteOnly
              ? 'Вы поддержали все заявки'
              : overdueOnly
                ? 'Просрочек нет'
                : isFiltered
                  ? 'Ничего не нашлось'
                  : 'Заявок пока нет'
          "
          :text="
            voteOnly
              ? 'Спасибо! Когда соседи сообщат о новой поломке, на вкладке «Заявки» появится цифра'
              : overdueOnly
                ? 'Все заявки пока в срок. Если что-то затянется, Кузя напомнит'
                : isFiltered
                  ? 'Попробуйте другой статус или слова для поиска'
                  : 'В доме всё спокойно. Заметили неполадку - сообщите, Кузя поможет'
          "
        >
          <v-btn v-if="voteOnly" color="primary" size="large" @click="setVoteOnly(false)">
            Показать все заявки
          </v-btn>
          <v-btn v-else color="primary" size="large" to="/issues/new" prepend-icon="mdi-plus">
            Сообщить о проблеме
          </v-btn>
        </EmptyState>
        <!-- Нижний отступ, чтобы плавающая кнопка не закрывала последнюю карточку -->
        <div v-else ref="list" class="pb-16">
          <AnimatedList class="flex flex-col gap-3">
            <div v-for="issue in items" :key="issue.id" data-stagger>
              <IssueCard :issue="issue" />
            </div>
          </AnimatedList>
        </div>
      </Transition>
    </div>

    <AppFab
      v-if="showFab"
      icon="mdi-plus"
      label="Сообщить"
      to="/issues/new"
      aria-label="Сообщить о проблеме"
    />
  </div>
</template>

<style scoped>
.vote-hint {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 52px;
  padding: 10px 14px;
  border: 0;
  border-radius: var(--r-lg);
  background: rgb(var(--v-theme-primary-container));
  color: rgb(var(--v-theme-on-primary-container));
  font: inherit;
}
.vote-hint__action {
  font-weight: 700;
  white-space: nowrap;
}
.vote-hint--on {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
</style>
