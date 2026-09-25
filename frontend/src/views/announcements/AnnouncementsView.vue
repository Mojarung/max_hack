<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { AnnouncementOut } from '@/api/types'
import AnnouncementCard from '@/components/announcements/AnnouncementCard.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import { useStagger } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { useAnnouncementsStore } from '@/stores/announcements'
import { useSessionStore } from '@/stores/session'

const store = useAnnouncementsStore()
const session = useSessionStore()
const list = ref<HTMLElement | null>(null)
useStagger(list, () => store.items.length)

const open = ref(false)
const title = ref('')
const text = ref('')
const pin = ref(false)
const saving = ref(false)
const busyId = ref<number | null>(null)
const canSave = computed(() => title.value.trim().length >= 3)

onMounted(() => void store.load())

function startCreate(): void {
  title.value = ''
  text.value = ''
  pin.value = session.isAdmin
  open.value = true
}

async function save(): Promise<void> {
  if (!canSave.value) return
  saving.value = true
  try {
    await store.create({ title: title.value.trim(), text: text.value.trim(), pin: pin.value })
    open.value = false
    notify.success(
      'Объявление опубликовано',
      session.me?.house.has_chat ? 'Кузя написал о нём в чат дома' : undefined,
    )
  } catch (e) {
    notify.error(e, 'Не получилось опубликовать')
  } finally {
    saving.value = false
  }
}

async function togglePin(item: AnnouncementOut): Promise<void> {
  busyId.value = item.id
  try {
    await store.setPinned(item.id, !item.pinned)
  } catch (e) {
    notify.error(e)
  } finally {
    busyId.value = null
  }
}

const toDelete = ref<AnnouncementOut | null>(null)
const deleteOpen = computed({
  get: () => toDelete.value !== null,
  set: (v: boolean) => {
    if (!v) toDelete.value = null
  },
})

async function remove(item: AnnouncementOut): Promise<void> {
  toDelete.value = null
  busyId.value = item.id
  try {
    await store.remove(item.id)
    notify.success('Объявление удалено')
  } catch (e) {
    notify.error(e)
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <div class="page page--with-fab">
    <p class="text-muted mt-0 mb-3">
      Важное для всего дома: отключения, работы, собрания. Кузя дублирует объявления в чат дома. В
      чате можно попросить: «Кузя, сделай объявление о субботнике в субботу в 11».
    </p>

    <ListSkeleton v-if="store.loading && !store.loaded" :count="3" />
    <ErrorState
      v-else-if="store.error && !store.items.length"
      :message="store.error"
      :retrying="store.loading"
      @retry="store.load()"
    />
    <EmptyState
      v-else-if="store.loaded && !store.items.length"
      title="Объявлений пока нет"
      text="Предупредите соседей об отключении воды или позовите на собрание"
    >
      <v-btn color="primary" size="large" prepend-icon="mdi-plus" @click="startCreate">
        Написать объявление
      </v-btn>
    </EmptyState>
    <div v-else ref="list" class="flex flex-col gap-3">
      <div v-for="item in store.items" :key="item.id" data-stagger>
        <AnnouncementCard :item="item">
          <div v-if="session.isAdmin || item.is_mine" class="mt-2 flex flex-wrap gap-2">
            <v-btn
              v-if="session.isAdmin"
              size="large"
              variant="tonal"
              color="primary"
              :prepend-icon="item.pinned ? 'mdi-pin-off-outline' : 'mdi-pin-outline'"
              :loading="busyId === item.id"
              @click="togglePin(item)"
            >
              {{ item.pinned ? 'Открепить' : 'Закрепить' }}
            </v-btn>
            <v-btn
              size="large"
              variant="text"
              prepend-icon="mdi-delete-outline"
              :disabled="busyId === item.id"
              @click="toDelete = item"
            >
              Удалить
            </v-btn>
          </div>
        </AnnouncementCard>
      </div>
    </div>

    <v-btn
      color="primary"
      size="large"
      rounded="xl"
      prepend-icon="mdi-plus"
      class="fab"
      @click="startCreate"
    >
      Объявление
    </v-btn>

    <Drawer v-model:open="deleteOpen">
      <DrawerContent>
        <DrawerHeader
          :title="`Удалить «${toDelete?.title ?? ''}»?`"
          description="Объявление пропадёт у всех соседей. Вернуть не получится."
        />
        <v-btn
          block
          size="x-large"
          color="deep"
          prepend-icon="mdi-delete-outline"
          @click="toDelete && remove(toDelete)"
        >
          Удалить
        </v-btn>
        <v-btn block size="large" variant="text" class="mt-1" @click="toDelete = null">
          Оставить
        </v-btn>
      </DrawerContent>
    </Drawer>

    <Drawer v-model:open="open">
      <DrawerContent>
        <DrawerHeader title="Новое объявление" description="Увидят все жители дома" />
        <form class="flex flex-col gap-3" @submit.prevent="save">
          <v-text-field
            v-model="title"
            label="Заголовок"
            placeholder="Например: Отключение воды 1 октября"
            maxlength="120"
            counter="120"
          />
          <v-textarea
            v-model="text"
            label="Подробности"
            placeholder="Когда, где и что нужно сделать соседям"
            rows="3"
            auto-grow
            maxlength="2000"
          />
          <v-switch
            v-if="session.isAdmin"
            v-model="pin"
            color="primary"
            inset
            hide-details
            label="Закрепить в чате и сверху списка"
          />
          <v-btn
            type="submit"
            block
            size="x-large"
            color="primary"
            :disabled="!canSave"
            :loading="saving"
            prepend-icon="mdi-bullhorn-outline"
          >
            Опубликовать
          </v-btn>
        </form>
      </DrawerContent>
    </Drawer>
  </div>
</template>
