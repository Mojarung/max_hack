<script setup lang="ts">
import { computed, ref } from 'vue'
import type { IssueDetail } from '@/api/types'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import { notify } from '@/lib/notify'
import { useIssuesStore } from '@/stores/issues'

type NextStatus = 'in_progress' | 'resolved' | 'rejected'

const props = defineProps<{ issue: IssueDetail }>()
const store = useIssuesStore()

const open = ref(false)
const target = ref<NextStatus>('resolved')
const note = ref('')
const saving = ref(false)

const OPTIONS: Record<NextStatus, { title: string; icon: string; color: string; hint: string }> = {
  in_progress: {
    title: 'Взяли в работу',
    icon: 'mdi-hammer-wrench',
    color: 'secondary',
    hint: 'Например: «Мастер придёт завтра до 12:00»',
  },
  resolved: {
    title: 'Проблема решена',
    icon: 'mdi-check-circle',
    color: 'success',
    hint: 'Например: «Кровлю залатали, течь устранена»',
  },
  rejected: {
    title: 'Отклонить',
    icon: 'mdi-close-circle-outline',
    color: 'grey',
    hint: 'Коротко объясните причину',
  },
}

const available = computed<NextStatus[]>(() =>
  props.issue.status === 'in_progress'
    ? ['resolved', 'rejected']
    : ['in_progress', 'resolved', 'rejected'],
)

function start(status: NextStatus): void {
  target.value = status
  note.value = ''
  open.value = true
}

async function save(): Promise<void> {
  saving.value = true
  try {
    await store.setStatus(props.issue.id, target.value, note.value.trim())
    open.value = false
    notify.success('Статус обновлён', 'Жители увидят изменения сразу')
  } catch (e) {
    notify.error(e, 'Статус не изменился')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="card-soft p-4" aria-label="Управление статусом">
    <h3 class="m-0 mb-1 text-base font-bold">Вы автор или администратор</h3>
    <p class="text-muted mt-0 mb-3 text-sm">Отметьте, как продвигается решение.</p>
    <div class="flex flex-col gap-2">
      <v-btn
        v-for="s in available"
        :key="s"
        :color="OPTIONS[s].color"
        variant="tonal"
        size="large"
        :prepend-icon="OPTIONS[s].icon"
        @click="start(s)"
      >
        {{ OPTIONS[s].title }}
      </v-btn>
    </div>

    <Drawer v-model:open="open">
      <DrawerContent>
        <DrawerHeader :title="OPTIONS[target].title" description="Комментарий увидят все жители" />
        <v-textarea
          v-model="note"
          :placeholder="OPTIONS[target].hint"
          rows="3"
          auto-grow
          counter="500"
          maxlength="500"
          label="Комментарий"
        />
        <v-btn
          block
          size="large"
          class="mt-3"
          :color="OPTIONS[target].color"
          :loading="saving"
          :prepend-icon="OPTIONS[target].icon"
          @click="save"
        >
          Сохранить
        </v-btn>
      </DrawerContent>
    </Drawer>
  </section>
</template>
