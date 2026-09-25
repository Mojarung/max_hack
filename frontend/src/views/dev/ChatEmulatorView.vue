<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { errorMessage } from '@/api/client'
import { devChatApi } from '@/api/endpoints'
import type { ChatButton, ChatMessage } from '@/api/types'
import ErrorState from '@/components/common/ErrorState.vue'
import DemoUserSwitcher from '@/components/layout/DemoUserSwitcher.vue'
import { Skeleton } from '@/components/ui/skeleton'
import { staggerIn } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { haptic, openLink } from '@/max/bridge'
import { deepLinkToPath } from '@/max/deeplink'
import { useDevChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { formatTime } from '@/utils/format'

const store = useDevChatStore()
const session = useSessionStore()
const router = useRouter()

const text = ref('')
const sending = ref(false)
const pressing = ref<string | null>(null)
const chatsError = ref<string | null>(null)
const list = ref<HTMLElement | null>(null)

const QUICK = [
  '/start',
  'Привет, Кузя!',
  'Создай субботник в субботу в 11 у площадки',
  'Какие проблемы в доме?',
  'Где ближайшее укрытие?',
  'Ты дурак, блин',
  'Заработок от 100000 в день, пиши в личку t.me/xxx',
]

const chatId = computed(() => store.currentChatId)
const messages = computed<ChatMessage[]>(() =>
  chatId.value === null ? [] : (store.messages[chatId.value] ?? []),
)
const me = computed(() => session.devUserId ?? session.me?.user.max_user_id ?? null)
const currentChat = computed(() => store.chats.find((c) => c.chat_id === chatId.value) ?? null)

const COLORS = ['#03045E', '#023E8A', '#0077B6', '#0096C7', '#00B4D8', '#48CAE4']
function nameColor(userId: number): string {
  return COLORS[Math.abs(userId) % COLORS.length]!
}

async function init(): Promise<void> {
  chatsError.value = null
  try {
    await store.loadChats()
    if (chatId.value !== null) await store.loadMessages(chatId.value)
  } catch (e) {
    chatsError.value = errorMessage(e)
  }
}
onMounted(init)

async function selectChat(id: number): Promise<void> {
  if (id === chatId.value) return
  haptic.selection()
  store.currentChatId = id
  await store.loadMessages(id)
}

async function scrollToEnd(): Promise<void> {
  await nextTick()
  staggerIn(list.value, '[data-msg]')
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
}
watch(() => messages.value.length, scrollToEnd)

async function send(value?: string): Promise<void> {
  const message = (value ?? text.value).trim()
  if (!message || chatId.value === null || me.value === null || sending.value) return
  sending.value = true
  const before = messages.value.length
  const target = chatId.value
  try {
    await devChatApi.send(target, me.value, message)
    if (value === undefined) text.value = ''
    haptic.impact('light')
    // Если SSE не успел доставить сообщение, добираем историю запросом
    setTimeout(() => {
      if ((store.messages[target]?.length ?? 0) === before) void store.loadMessages(target)
    }, 1500)
  } catch (e) {
    notify.error(e, 'Сообщение не отправлено')
  } finally {
    sending.value = false
  }
}

async function press(message: ChatMessage, button: ChatButton): Promise<void> {
  haptic.impact('light')
  if (button.type === 'link') {
    const url = button.url ?? button.payload
    if (url) openLink(url)
    return
  }
  if (button.type === 'open_app') {
    const path = deepLinkToPath(button.payload ?? '')
    if (path) await router.push(path)
    else notify.warning('Не знаю, какой раздел открыть')
    return
  }
  if (chatId.value === null || me.value === null) return
  const key = `${message.id}:${button.payload}`
  pressing.value = key
  try {
    await devChatApi.callback(chatId.value, me.value, message.id, button.payload ?? '')
  } catch (e) {
    notify.error(e, 'Кнопка не сработала')
  } finally {
    pressing.value = null
  }
}

function buttonIcon(type: ChatButton['type']): string | undefined {
  if (type === 'link') return 'mdi-open-in-new'
  if (type === 'open_app') return 'mdi-application-outline'
  return undefined
}
</script>

<template>
  <div class="page chat-page">
    <div class="mb-2 flex items-center justify-between gap-2">
      <span class="text-muted text-sm">Вы пишете как:</span>
      <DemoUserSwitcher />
    </div>

    <ErrorState v-if="chatsError" :message="chatsError" @retry="init" />

    <template v-else>
      <div class="chips-scroll" role="tablist" aria-label="Чаты">
        <v-chip
          v-for="c in store.chats"
          :key="c.chat_id"
          size="large"
          role="tab"
          :aria-selected="c.chat_id === chatId"
          :color="c.chat_id === chatId ? 'primary' : undefined"
          :variant="c.chat_id === chatId ? 'flat' : 'outlined'"
          :prepend-icon="c.type === 'chat' ? 'mdi-account-group' : 'mdi-robot-happy-outline'"
          @click="selectChat(c.chat_id)"
        >
          {{ c.title }}
        </v-chip>
      </div>

      <section class="chat" :aria-label="currentChat?.title ?? 'Чат'">
        <div v-if="store.loading && !messages.length" class="flex flex-col gap-2 p-2">
          <Skeleton
            v-for="i in 4"
            :key="i"
            class="h-12 rounded-2xl"
            :class="i % 2 ? 'w-3/5' : 'ml-auto w-1/2'"
          />
        </div>
        <p v-else-if="!messages.length" class="text-muted p-6 text-center text-sm">
          Сообщений пока нет. Начните с /start или нажмите подсказку ниже.
        </p>
        <div ref="list" class="flex flex-col gap-1.5" aria-live="polite">
          <div
            v-for="m in messages"
            :key="m.id"
            data-msg
            class="flex items-end gap-2"
            :class="{ 'flex-row-reverse': m.from?.user_id === me }"
          >
            <img
              v-if="!m.from"
              src="/kuzya-avatar.svg"
              loading="lazy"
              decoding="async"
              alt=""
              width="30"
              height="30"
              class="shrink-0 rounded-full"
            />
            <span
              v-else-if="m.from.user_id !== me"
              class="avatar"
              :style="{ background: nameColor(m.from.user_id) }"
              aria-hidden="true"
            >
              {{ m.from.name.slice(0, 1) }}
            </span>
            <div class="max-w-[82%]">
              <div
                class="msg"
                :class="{
                  'msg--bot': !m.from,
                  'msg--me': m.from?.user_id === me,
                  'msg--deleted': m.deleted,
                }"
              >
                <div
                  v-if="!m.deleted && m.from?.user_id !== me"
                  class="mb-0.5 text-sm font-bold"
                  :style="{
                    color: m.from ? nameColor(m.from.user_id) : 'rgb(var(--v-theme-primary))',
                  }"
                >
                  {{ m.from ? m.from.name : 'Кузя (бот)' }}
                </div>
                <div v-if="m.deleted" class="flex items-center gap-1">
                  <v-icon icon="mdi-cancel" size="16" /> Сообщение удалено модератором Кузей
                </div>
                <template v-else>
                  <div v-if="m.photos?.length" class="mb-1 flex gap-1">
                    <img
                      v-for="src in m.photos"
                      :key="src"
                      :src="src"
                      alt="Фото к сообщению"
                      class="h-[120px] min-w-0 flex-1 rounded-xl object-cover"
                      loading="lazy"
                    />
                  </div>
                  <div class="pre-wrap">{{ m.text }}</div>
                </template>
                <div class="mt-0.5 text-right text-sm opacity-60">
                  {{ formatTime(m.created_at) }}
                </div>
              </div>
              <div v-if="m.notice" class="text-muted mt-1 flex items-center gap-1 px-1 text-sm">
                <v-icon icon="mdi-shield-check-outline" size="14" /> {{ m.notice }}
              </div>
              <div v-if="m.buttons?.length && !m.deleted" class="mt-1 flex flex-col gap-1">
                <div v-for="(row, ri) in m.buttons" :key="ri" class="flex gap-1">
                  <v-btn
                    v-for="b in row"
                    :key="`${b.type}:${b.text}:${b.payload}`"
                    class="flex-1"
                    variant="tonal"
                    color="primary"
                    size="default"
                    :append-icon="buttonIcon(b.type)"
                    :loading="pressing === `${m.id}:${b.payload}`"
                    @click="press(m, b)"
                  >
                    {{ b.text }}
                  </v-btn>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </template>

    <div class="composer-wrap">
      <div class="chips-scroll mb-2">
        <v-chip
          v-for="q in QUICK"
          :key="q"
          size="small"
          variant="outlined"
          :disabled="sending || chatId === null"
          @click="send(q)"
        >
          {{ q }}
        </v-chip>
      </div>
      <form class="flex items-end gap-2" @submit.prevent="send()">
        <v-textarea
          v-model="text"
          placeholder="Сообщение"
          rows="1"
          auto-grow
          max-rows="4"
          density="comfortable"
          hide-details
          aria-label="Текст сообщения"
          class="flex-1"
          @keydown.enter.exact.prevent="send()"
        />
        <v-btn
          type="submit"
          icon="mdi-send"
          color="primary"
          size="large"
          :loading="sending"
          :disabled="!text.trim() || chatId === null"
          aria-label="Отправить"
        />
      </form>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  padding-bottom: calc(var(--app-nav-height) + 150px + env(safe-area-inset-bottom));
}
.chat {
  margin-top: 8px;
  padding: 10px 8px;
  min-height: 50dvh;
  border-radius: var(--radius-card);
  background:
    radial-gradient(circle at 20% 10%, rgba(var(--v-theme-primary), 0.06), transparent 40%),
    rgba(var(--v-theme-on-surface), 0.04);
}
.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 50%;
  color: #caf0f8;
  font-weight: 700;
  font-size: 14px;
}
.msg {
  padding: 7px 12px;
  border-radius: 16px 16px 16px 4px;
  font-size: 15.5px;
  line-height: 1.38;
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 1px 1px rgba(16, 24, 40, 0.08);
}
.msg--bot {
  background: rgba(var(--v-theme-primary), 0.1);
}
.msg--me {
  border-radius: 16px 16px 4px 16px;
  color: rgb(var(--v-theme-on-primary));
  background: rgb(var(--v-theme-primary));
}
.msg--deleted {
  font-style: italic;
  color: rgba(var(--v-theme-on-surface), 0.55);
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.composer-wrap {
  position: fixed;
  left: 0;
  right: 0;
  bottom: calc(var(--app-nav-height) + env(safe-area-inset-bottom));
  z-index: 900;
  max-width: var(--app-max-width);
  margin: 0 auto;
  padding: 8px 16px 10px;
  background: rgba(var(--v-theme-background), 0.94);
  backdrop-filter: blur(10px);
}
</style>
