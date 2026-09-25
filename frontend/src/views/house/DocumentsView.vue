<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { errorMessage } from '@/api/client'
import { documentsApi } from '@/api/endpoints'
import type { DocumentOut, DocumentScope } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import { notify } from '@/lib/notify'
import { openLink } from '@/max/bridge'
import { useSessionStore } from '@/stores/session'
import { formatDate } from '@/utils/format'

const session = useSessionStore()
const tab = ref<DocumentScope>('house')
const items = ref<DocumentOut[]>([])
const loading = ref(false)
const loaded = ref(false)
const error = ref<string | null>(null)
const busyId = ref<number | null>(null)

const open = ref(false)
const file = ref<File | null>(null)
const title = ref('')
const scope = ref<DocumentScope>('personal')
const progress = ref(0)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.odt,.txt,image/jpeg,image/png,image/webp,image/heic'
const canUpload = computed(() => !!file.value && title.value.trim().length >= 2)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    items.value = await documentsApi.list(tab.value)
    loaded.value = true
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(tab, () => {
  loaded.value = false
  void load()
})

function icon(d: DocumentOut): string {
  if (d.content_type === 'application/pdf') return 'mdi-file-pdf-box'
  if (d.content_type.startsWith('image/')) return 'mdi-file-image-outline'
  if (d.content_type.includes('sheet') || d.content_type.includes('excel'))
    return 'mdi-file-excel-outline'
  if (d.content_type.includes('word') || d.content_type.includes('opendocument'))
    return 'mdi-file-word-outline'
  return 'mdi-file-document-outline'
}

function size(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`
  return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} МБ`
}

async function openDoc(d: DocumentOut): Promise<void> {
  busyId.value = d.id
  try {
    const { url } = await documentsApi.link(d.id)
    openLink(url.startsWith('/') ? `${window.location.origin}${url}` : url)
  } catch (e) {
    notify.error(e, 'Не удалось открыть документ')
  } finally {
    busyId.value = null
  }
}

async function remove(d: DocumentOut): Promise<void> {
  busyId.value = d.id
  try {
    await documentsApi.remove(d.id)
    items.value = items.value.filter((x) => x.id !== d.id)
    notify.success('Документ удалён')
  } catch (e) {
    notify.error(e)
  } finally {
    busyId.value = null
  }
}

function startUpload(): void {
  file.value = null
  title.value = ''
  progress.value = 0
  scope.value = tab.value === 'house' && session.isAdmin ? 'house' : 'personal'
  open.value = true
}

function onFile(event: Event): void {
  const picked = (event.target as HTMLInputElement).files?.[0] ?? null
  file.value = picked
  if (picked && !title.value.trim()) title.value = picked.name.replace(/\.[^.]+$/, '').slice(0, 200)
}

async function upload(): Promise<void> {
  if (!canUpload.value || !file.value) return
  uploading.value = true
  const form = new FormData()
  form.append('file', file.value)
  form.append('title', title.value.trim())
  form.append('scope', scope.value)
  try {
    await documentsApi.upload(form, (f) => (progress.value = Math.round(f * 100)))
    open.value = false
    notify.success(
      'Документ загружен',
      scope.value === 'house' ? 'Его видят все жители дома' : 'Его видите только вы',
    )
    if (tab.value !== scope.value) tab.value = scope.value
    else void load()
  } catch (e) {
    notify.error(e, 'Не удалось загрузить')
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="page">
    <v-btn-toggle
      v-model="tab"
      mandatory
      divided
      color="primary"
      variant="outlined"
      class="doc-tabs mb-3 w-full"
      aria-label="Какие документы показать"
    >
      <v-btn value="house" class="flex-1" prepend-icon="mdi-home-city-outline">Дома</v-btn>
      <v-btn value="personal" class="flex-1" prepend-icon="mdi-lock-outline">Мои</v-btn>
    </v-btn-toggle>
    <p class="text-muted mt-0 mb-3 text-sm">
      {{
        tab === 'house'
          ? 'Протоколы собраний, договор с УК, акты. Видят все жители дома, загружает администратор.'
          : 'Ваши личные документы: видите только вы. Ссылка на файл работает 15 минут.'
      }}
    </p>

    <ListSkeleton v-if="loading && !loaded" :count="3" />
    <ErrorState v-else-if="error" :message="error" :retrying="loading" @retry="load" />
    <EmptyState
      v-else-if="loaded && !items.length"
      :title="tab === 'house' ? 'Документов дома пока нет' : 'Личных документов нет'"
      :text="
        tab === 'house'
          ? session.isAdmin
            ? 'Загрузите протокол собрания или договор с УК'
            : 'Администратор дома ещё ничего не загрузил'
          : 'Храните здесь квитанции, акты и паспорт квартиры'
      "
    >
      <v-btn
        v-if="tab === 'personal' || session.isAdmin"
        color="primary"
        size="large"
        prepend-icon="mdi-upload"
        @click="startUpload"
      >
        Загрузить
      </v-btn>
    </EmptyState>
    <ul v-else class="m-0 flex list-none flex-col gap-2 p-0">
      <li v-for="d in items" :key="d.id" class="card-soft flex items-center gap-2 p-2 pl-3">
        <button
          type="button"
          class="doc-row min-w-0 flex-1"
          :disabled="busyId === d.id"
          :aria-label="`Открыть ${d.title}`"
          @click="openDoc(d)"
        >
          <v-icon :icon="icon(d)" size="32" color="primary" aria-hidden="true" />
          <span class="min-w-0 flex-1 text-left">
            <span class="block truncate font-semibold">{{ d.title }}</span>
            <span class="text-muted block truncate text-sm"
              >{{ formatDate(d.created_at) }} · {{ size(d.size) }}</span
            >
          </span>
          <v-progress-circular
            v-if="busyId === d.id"
            indeterminate
            size="20"
            width="2"
            color="primary"
          />
        </button>
        <v-btn
          v-if="d.can_delete"
          icon="mdi-delete-outline"
          variant="text"
          :aria-label="`Удалить ${d.title}`"
          :disabled="busyId === d.id"
          @click="remove(d)"
        />
      </li>
    </ul>

    <v-btn
      v-if="tab === 'personal' || session.isAdmin"
      color="primary"
      size="large"
      rounded="xl"
      prepend-icon="mdi-upload"
      class="fab"
      @click="startUpload"
    >
      Загрузить
    </v-btn>

    <Drawer v-model:open="open">
      <DrawerContent>
        <DrawerHeader title="Новый документ" description="PDF, Word, Excel или фото до 20 МБ" />
        <form class="flex flex-col gap-3" @submit.prevent="upload">
          <input
            ref="fileInput"
            type="file"
            class="sr-only"
            :accept="ACCEPT"
            aria-label="Выбрать файл"
            @change="onFile"
          />
          <v-btn
            variant="tonal"
            color="primary"
            size="large"
            prepend-icon="mdi-paperclip"
            class="justify-start"
            @click="fileInput?.click()"
          >
            <span class="truncate">{{ file ? file.name : 'Выбрать файл' }}</span>
          </v-btn>
          <v-text-field v-model="title" label="Название" maxlength="200" />
          <v-radio-group v-if="session.isAdmin" v-model="scope" hide-details>
            <v-radio value="house" label="Документ дома: видят все жители" color="primary" />
            <v-radio value="personal" label="Личный: вижу только я" color="primary" />
          </v-radio-group>
          <v-progress-linear
            v-if="uploading"
            :model-value="progress"
            color="primary"
            height="8"
            aria-label="Загрузка файла"
          />
          <v-btn
            type="submit"
            block
            size="x-large"
            color="primary"
            :disabled="!canUpload"
            :loading="uploading"
            prepend-icon="mdi-upload"
          >
            Загрузить
          </v-btn>
        </form>
      </DrawerContent>
    </Drawer>
  </div>
</template>

<style scoped>
.doc-tabs {
  height: 48px;
}
.doc-row {
  display: flex;
  min-height: 52px;
  align-items: center;
  gap: 12px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
}
.fab {
  position: fixed;
  right: max(16px, calc((100vw - var(--app-max-width)) / 2 + 16px));
  bottom: calc(var(--app-nav-height) + 16px + env(safe-area-inset-bottom));
  z-index: 900;
  box-shadow: 0 8px 24px -6px rgba(var(--v-theme-primary), 0.6);
}
</style>
