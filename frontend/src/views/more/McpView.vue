<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { errorMessage } from '@/api/client'
import { mcpApi } from '@/api/endpoints'
import { MCP_NAME_RE, type McpServerOut, type McpTool, type McpTransport } from '@/api/types'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import ListSkeleton from '@/components/common/ListSkeleton.vue'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import { notify } from '@/lib/notify'

const servers = ref<McpServerOut[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const tools = ref<Record<number, McpTool[]>>({})
const toolsLoading = ref<number | null>(null)
const toolsError = ref<Record<number, string>>({})
const expanded = ref<number[]>([])

const formOpen = ref(false)
const name = ref('')
const transport = ref<McpTransport>('streamable_http')
const url = ref('')
const headersText = ref('')
const saving = ref(false)
const showErrors = ref(false)

const deleting = ref<McpServerOut | null>(null)
const deleteBusy = ref(false)

const TRANSPORTS = [
  { value: 'streamable_http', title: 'Streamable HTTP' },
  { value: 'sse', title: 'SSE' },
]

function parseHeaders(raw: string): Record<string, string> | null {
  const result: Record<string, string> = {}
  for (const line of raw.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const index = trimmed.indexOf(':')
    if (index <= 0) return null
    result[trimmed.slice(0, index).trim()] = trimmed.slice(index + 1).trim()
  }
  return result
}

const errors = computed(() => ({
  name: MCP_NAME_RE.test(name.value)
    ? ''
    : 'Латиница в нижнем регистре, цифры и _, начинается с буквы',
  url: /^https?:\/\/\S+$/.test(url.value.trim()) ? '' : 'Адрес вида https://example.com/mcp',
  headers: parseHeaders(headersText.value) === null ? 'Каждая строка: Имя: значение' : '',
}))

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    servers.value = await mcpApi.list()
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function loadTools(id: number): Promise<void> {
  if (tools.value[id] || toolsLoading.value === id) return
  toolsLoading.value = id
  const nextErrors = { ...toolsError.value }
  delete nextErrors[id]
  toolsError.value = nextErrors
  try {
    const list = await mcpApi.tools(id)
    tools.value = { ...tools.value, [id]: list }
  } catch (e) {
    toolsError.value = { ...toolsError.value, [id]: errorMessage(e) }
  } finally {
    toolsLoading.value = null
  }
}

function onExpand(value: unknown): void {
  const ids = (Array.isArray(value) ? value : [value]).filter(
    (v): v is number => typeof v === 'number',
  )
  expanded.value = ids
  ids.forEach((id) => void loadTools(id))
}

function openForm(): void {
  name.value = ''
  url.value = ''
  headersText.value = ''
  transport.value = 'streamable_http'
  showErrors.value = false
  formOpen.value = true
}

async function save(): Promise<void> {
  showErrors.value = true
  const headers = parseHeaders(headersText.value)
  if (errors.value.name || errors.value.url || !headers) return
  saving.value = true
  try {
    const created = await mcpApi.create({
      name: name.value,
      transport: transport.value,
      url: url.value.trim(),
      headers,
    })
    servers.value = [...servers.value, created]
    formOpen.value = false
    notify.success('MCP-сервер добавлен', 'Кузя сможет пользоваться его инструментами')
  } catch (e) {
    notify.error(e, 'Сервер не добавлен')
  } finally {
    saving.value = false
  }
}

async function remove(): Promise<void> {
  if (!deleting.value) return
  deleteBusy.value = true
  const id = deleting.value.id
  try {
    await mcpApi.remove(id)
    servers.value = servers.value.filter((s) => s.id !== id)
    deleting.value = null
    notify.success('Сервер удалён')
  } catch (e) {
    notify.error(e, 'Не удалось удалить')
  } finally {
    deleteBusy.value = false
  }
}
</script>

<template>
  <div class="page">
    <p class="text-muted mt-0 text-sm">
      MCP-серверы дают ИИ-помощнику Кузе новые инструменты: поиск по базе УК, погода, карты.
    </p>

    <ListSkeleton v-if="loading && !servers.length" :count="2" />
    <ErrorState
      v-else-if="error && !servers.length"
      :message="error"
      :retrying="loading"
      @retry="load"
    />
    <EmptyState
      v-else-if="!servers.length"
      title="Серверов пока нет"
      text="Добавьте первый MCP-сервер"
    />

    <v-expansion-panels
      v-else
      :model-value="expanded"
      multiple
      variant="accordion"
      @update:model-value="onExpand"
    >
      <v-expansion-panel
        v-for="s in servers"
        :key="s.id"
        :value="s.id"
        rounded="xl"
        elevation="0"
        class="card-soft mb-2"
      >
        <v-expansion-panel-title>
          <div class="flex min-w-0 flex-1 items-center gap-3">
            <v-icon
              :icon="s.enabled ? 'mdi-power-plug' : 'mdi-power-plug-off'"
              :color="s.enabled ? 'success' : 'grey'"
            />
            <div class="min-w-0">
              <div class="font-semibold">{{ s.name }}</div>
              <div class="text-muted truncate text-xs">{{ s.transport }} · {{ s.url }}</div>
            </div>
          </div>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="text-muted mb-2 text-sm">
            {{ s.enabled ? 'Включён' : 'Выключен'
            }}<template v-if="s.has_headers"> · с заголовками авторизации</template>
          </div>
          <div v-if="toolsLoading === s.id" class="flex items-center gap-2 text-sm">
            <v-progress-circular indeterminate size="18" width="2" /> Загружаем инструменты...
          </div>
          <div v-else-if="toolsError[s.id]" class="text-sm text-error" role="alert">
            {{ toolsError[s.id] }}
          </div>
          <template v-else-if="tools[s.id]">
            <div class="mb-1 text-sm font-semibold">Инструменты: {{ tools[s.id]!.length }}</div>
            <ul class="m-0 flex list-none flex-col gap-1.5 p-0">
              <li
                v-for="t in tools[s.id]"
                :key="t.name"
                class="rounded-lg bg-surface-variant px-3 py-2"
              >
                <code class="text-sm font-semibold">{{ t.name }}</code>
                <div v-if="t.description" class="text-muted text-xs">{{ t.description }}</div>
              </li>
            </ul>
          </template>
          <v-btn
            variant="text"
            color="error"
            class="mt-2"
            prepend-icon="mdi-delete-outline"
            @click="deleting = s"
          >
            Удалить
          </v-btn>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <v-btn
      block
      size="large"
      color="primary"
      class="mt-4"
      prepend-icon="mdi-plus"
      @click="openForm"
    >
      Добавить сервер
    </v-btn>

    <Drawer v-model:open="formOpen">
      <DrawerContent>
        <DrawerHeader title="Новый MCP-сервер" />
        <form class="flex flex-col gap-3" novalidate @submit.prevent="save">
          <v-text-field
            v-model="name"
            label="Имя"
            placeholder="weather"
            autocapitalize="off"
            :error-messages="showErrors ? errors.name : ''"
          />
          <v-select v-model="transport" :items="TRANSPORTS" label="Транспорт" />
          <v-text-field
            v-model="url"
            label="Адрес"
            placeholder="https://mcp.example.com/mcp"
            inputmode="url"
            :error-messages="showErrors ? errors.url : ''"
          />
          <v-textarea
            v-model="headersText"
            label="Заголовки (необязательно)"
            placeholder="Authorization: Bearer ..."
            rows="2"
            auto-grow
            :error-messages="showErrors ? errors.headers : ''"
          />
          <v-btn type="submit" block size="large" color="primary" :loading="saving"
            >Сохранить</v-btn
          >
        </form>
      </DrawerContent>
    </Drawer>

    <v-dialog :model-value="!!deleting" max-width="400" @update:model-value="deleting = null">
      <v-card
        rounded="xl"
        :title="`Удалить «${deleting?.name}»?`"
        text="Кузя перестанет пользоваться инструментами этого сервера."
      >
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleting = null">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleteBusy" @click="remove">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
