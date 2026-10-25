<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { errorMessage } from '@/api/client'
import { devChatApi } from '@/api/endpoints'
import type { ChatButton, ChatMessage } from '@/api/types'
import ErrorState from '@/components/common/ErrorState.vue'
import { Skeleton } from '@/components/ui/skeleton'
import { staggerIn } from '@/composables/useMotion'
import { notify } from '@/lib/notify'
import { haptic, openLink } from '@/max/bridge'
import { deepLinkToPath } from '@/max/deeplink'
import { goBack } from '@/router'
import { useDevChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { boldSegments, formatDate, formatTime, fullName } from '@/utils/format'

/**
 * Эмулятор чата MAX: экран один в один как у настоящего мессенджера, чтобы на демо и
 * в презентации бот выглядел так, как его увидит житель. Служебное (выбор чата и жителя)
 * спрятано в меню «⋮» в шапке, подсказки с командами - за синей кнопкой меню бота.
 */

const store = useDevChatStore()
const session = useSessionStore()
const router = useRouter()

const text = ref('')
const sending = ref(false)
const pressing = ref<string | null>(null)
const chatsError = ref<string | null>(null)
const scroller = ref<HTMLElement | null>(null)
const list = ref<HTMLElement | null>(null)
const quickOpen = ref(false)

// Команды подписаны по-человечески: житель видит «Меню», а боту уходит «/меню»
const QUICK: { label: string; text: string }[] = [
  { label: 'Меню', text: '/меню' },
  { label: 'Новая заявка', text: '/новая' },
  { label: 'Заявки дома', text: '/проблемы' },
  { label: '/start', text: '/start' },
  ...[
    'Привет, Кузя!',
    'Создай субботник в субботу в 11 у площадки',
    'Какие проблемы в доме?',
    'Где ближайшее укрытие?',
    'Ты дурак, блин',
    'Заработок от 100000 в день, пиши в личку t.me/xxx',
  ].map((text) => ({ label: text, text })),
]

const chatId = computed(() => store.currentChatId)
const messages = computed<ChatMessage[]>(() =>
  chatId.value === null ? [] : (store.messages[chatId.value] ?? []),
)
const me = computed(() => session.devUserId ?? session.me?.user.max_user_id ?? null)
const currentChat = computed(() => store.chats.find((c) => c.chat_id === chatId.value) ?? null)
const isDialog = computed(() => currentChat.value?.type !== 'chat')
const headerTitle = computed(() => (isDialog.value ? 'Кузя' : (currentChat.value?.title ?? 'Чат')))

const COLORS = ['#03045E', '#023E8A', '#0077B6', '#0096C7', '#00B4D8', '#48CAE4']
function nameColor(userId: number): string {
  return COLORS[Math.abs(userId) % COLORS.length]!
}

/** Подпись дня над первым сообщением дня, как разделители дат в MAX. */
function dayLabel(index: number): string | null {
  const current = messages.value[index]
  if (!current) return null
  const day = (value: string) => new Date(value).toDateString()
  const previous = messages.value[index - 1]
  if (previous && day(previous.created_at) === day(current.created_at)) return null
  const today = new Date()
  const yesterday = new Date(today.getTime() - 86_400_000)
  const stamp = day(current.created_at)
  if (stamp === today.toDateString()) return 'Сегодня'
  if (stamp === yesterday.toDateString()) return 'Вчера'
  return formatDate(current.created_at)
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

const switching = ref(false)
async function pickUser(id: number): Promise<void> {
  if (id === session.devUserId) return
  switching.value = true
  try {
    await session.switchUser(id)
  } finally {
    switching.value = false
  }
}

/** Сколько сообщений уже было на экране: лесенкой проявляем только новые, а не всю историю. */
let shownCount = 0
const ANIMATE_UP_TO = 6

async function scrollToEnd(): Promise<void> {
  await nextTick()
  const added = messages.value.length - shownCount
  shownCount = messages.value.length
  const history = added > ANIMATE_UP_TO
  if (history) {
    list.value
      ?.querySelectorAll<HTMLElement>('[data-msg]')
      .forEach((el) => (el.dataset.shown = '1'))
  } else {
    staggerIn(list.value, '[data-msg]')
  }
  const el = scroller.value
  if (el) el.scrollTo({ top: el.scrollHeight, behavior: history ? 'auto' : 'smooth' })
}
watch(() => messages.value.length, scrollToEnd)
watch(chatId, () => {
  shownCount = 0
  void scrollToEnd()
})

/** Фото к сообщению: уменьшаем в браузере до 1280 px, чтобы не гонять мегабайты через эмулятор. */
const photos = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const MAX_PHOTOS = 3

function shrink(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, 1280 / Math.max(img.width, img.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.round(img.width * scale)
      canvas.height = Math.round(img.height * scale)
      canvas.getContext('2d')?.drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(img.src)
      resolve(canvas.toDataURL('image/jpeg', 0.85))
    }
    img.onerror = () => reject(new Error('Не удалось прочитать фото'))
    img.src = URL.createObjectURL(file)
  })
}

async function onPhotos(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? []).slice(0, MAX_PHOTOS - photos.value.length)
  input.value = ''
  try {
    photos.value = [...photos.value, ...(await Promise.all(files.map(shrink)))]
  } catch (e) {
    notify.error(e, 'Фото не добавлено')
  }
}

async function send(value?: string): Promise<void> {
  const message = (value ?? text.value).trim()
  const attached = value === undefined ? photos.value : []
  if ((!message && !attached.length) || chatId.value === null || me.value === null || sending.value)
    return
  sending.value = true
  quickOpen.value = false
  const before = messages.value.length
  const target = chatId.value
  try {
    await devChatApi.send(target, me.value, message, attached)
    if (value === undefined) {
      text.value = ''
      photos.value = []
    }
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
  <div class="max-screen">
    <!-- Шапка как у чата с ботом в MAX: назад, аватар, имя с галочкой, подпись -->
    <header class="max-header">
      <v-btn icon="mdi-arrow-left" variant="text" size="large" aria-label="Назад" @click="goBack" />
      <img
        v-if="isDialog"
        src="/kuzya-avatar.png"
        alt=""
        width="40"
        height="40"
        class="max-header__avatar"
      />
      <span v-else class="max-header__avatar max-header__avatar--group" aria-hidden="true">
        <v-icon icon="mdi-account-group" size="22" />
      </span>
      <div class="min-w-0 flex-1">
        <div class="max-header__name">
          <span class="truncate">{{ headerTitle }}</span>
          <v-icon v-if="isDialog" icon="mdi-check-decagram" size="18" class="max-header__check" />
        </div>
        <div class="max-header__sub">{{ isDialog ? 'Бот' : 'Чат дома · Кузя в чате' }}</div>
      </div>
      <v-menu location="bottom end" max-height="76dvh">
        <template #activator="{ props: activator }">
          <v-btn
            v-bind="activator"
            icon="mdi-dots-vertical"
            variant="text"
            size="large"
            aria-label="Меню эмулятора: выбрать чат и жителя"
          />
        </template>
        <v-list density="comfortable" min-width="280" nav>
          <v-list-subheader>Чат</v-list-subheader>
          <v-list-item
            v-for="c in store.chats"
            :key="c.chat_id"
            :active="c.chat_id === chatId"
            color="primary"
            :title="c.title"
            :subtitle="c.type === 'chat' ? 'групповой чат дома' : 'личные сообщения с ботом'"
            :prepend-icon="c.type === 'chat' ? 'mdi-account-group' : 'mdi-robot-happy-outline'"
            @click="selectChat(c.chat_id)"
          />
          <template v-if="!session.inMax && session.devUsers.length">
            <v-divider class="my-1" />
            <v-list-subheader>Писать как (демо)</v-list-subheader>
            <v-list-item
              v-for="u in session.devUsers"
              :key="u.max_user_id"
              :active="u.max_user_id === session.devUserId"
              color="primary"
              :title="fullName(u)"
              :subtitle="
                [
                  u.apartment ? `кв. ${u.apartment}` : null,
                  u.role === 'admin' ? 'администратор' : null,
                ]
                  .filter(Boolean)
                  .join(' · ')
              "
              :disabled="switching"
              @click="pickUser(u.max_user_id)"
            >
              <template #append>
                <v-icon
                  v-if="u.max_user_id === session.devUserId"
                  icon="mdi-check"
                  color="primary"
                />
              </template>
            </v-list-item>
          </template>
        </v-list>
      </v-menu>
    </header>

    <ErrorState v-if="chatsError" :message="chatsError" class="max-error" @retry="init" />

    <section
      v-else
      ref="scroller"
      class="max-chat"
      :aria-label="currentChat?.title ?? 'Чат'"
      role="log"
      aria-live="polite"
    >
      <div v-if="store.loading && !messages.length" class="flex flex-col gap-2 p-3">
        <Skeleton
          v-for="i in 4"
          :key="i"
          class="h-12 rounded-2xl"
          :class="i % 2 ? 'w-3/5' : 'ml-auto w-1/2'"
        />
      </div>
      <div v-else-if="!messages.length" class="max-sys">
        {{ isDialog ? 'Вы начали общение с ботом' : 'Сообщений пока нет' }}
      </div>
      <div ref="list" class="max-chat__inner">
        <div v-if="messages.length && isDialog" class="max-sys">Вы начали общение с ботом</div>
        <template v-for="(m, index) in messages" :key="m.id">
          <div v-if="dayLabel(index)" class="max-sys">{{ dayLabel(index) }}</div>
          <div data-msg class="max-row" :class="{ 'max-row--out': m.from?.user_id === me }">
            <img
              v-if="!m.from && !isDialog"
              src="/kuzya-avatar.png"
              loading="lazy"
              decoding="async"
              alt=""
              width="32"
              height="32"
              class="max-avatar"
            />
            <span
              v-else-if="m.from && m.from.user_id !== me && !isDialog"
              class="max-avatar max-avatar--letter"
              :style="{ background: nameColor(m.from.user_id) }"
              aria-hidden="true"
            >
              {{ m.from.name.slice(0, 1) }}
            </span>
            <div class="max-col">
              <div
                class="max-msg"
                :class="{
                  'max-msg--out': m.from?.user_id === me,
                  'max-msg--deleted': m.deleted,
                  'max-msg--photo': m.photos?.length && !m.deleted,
                }"
              >
                <div
                  v-if="!m.deleted && m.from && m.from.user_id !== me && !isDialog"
                  class="max-msg__name"
                  :style="{ color: nameColor(m.from.user_id) }"
                >
                  {{ m.from.name }}
                </div>
                <div v-if="m.deleted" class="flex items-center gap-1">
                  <v-icon icon="mdi-cancel" size="16" /> Сообщение удалено модератором Кузей
                </div>
                <template v-else>
                  <div v-if="m.photos?.length" class="max-msg__photos">
                    <img
                      v-for="src in m.photos"
                      :key="src"
                      :src="src"
                      alt="Фото к сообщению"
                      loading="lazy"
                    />
                  </div>
                  <div class="max-msg__text pre-wrap">
                    <template v-for="(part, i) in boldSegments(m.text)" :key="i">
                      <b v-if="part.bold">{{ part.text }}</b>
                      <template v-else>{{ part.text }}</template>
                    </template>
                    <span class="max-msg__time">{{ formatTime(m.created_at) }}</span>
                  </div>
                </template>
              </div>
              <div v-if="m.notice" class="max-notice">
                <v-icon icon="mdi-shield-check-outline" size="14" /> {{ m.notice }}
              </div>
              <div v-if="m.buttons?.length && !m.deleted" class="max-keys">
                <div v-for="(row, ri) in m.buttons" :key="ri" class="max-keys__row">
                  <button
                    v-for="b in row"
                    :key="`${b.type}:${b.text}:${b.payload}`"
                    type="button"
                    class="max-key"
                    :disabled="pressing === `${m.id}:${b.payload}`"
                    @click="press(m, b)"
                  >
                    <span class="truncate">{{ b.text }}</span>
                    <v-progress-circular
                      v-if="pressing === `${m.id}:${b.payload}`"
                      indeterminate
                      size="16"
                      width="2"
                    />
                    <v-icon v-else-if="buttonIcon(b.type)" :icon="buttonIcon(b.type)" size="16" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </section>

    <footer class="max-composer">
      <!-- Меню бота: в MAX за синей кнопкой список команд, здесь готовые фразы для демо -->
      <div v-if="quickOpen" class="max-quick chips-scroll">
        <button
          v-for="q in QUICK"
          :key="q.text"
          type="button"
          class="max-quick__item"
          :disabled="sending || chatId === null"
          @click="send(q.text)"
        >
          {{ q.label }}
        </button>
      </div>
      <div v-if="photos.length" class="px-3 pb-1">
        <v-chip prepend-icon="mdi-image-outline" closable size="small" @click:close="photos = []">
          Фото: {{ photos.length }}
        </v-chip>
      </div>
      <input
        ref="fileInput"
        type="file"
        accept="image/*"
        multiple
        class="sr-only"
        tabindex="-1"
        aria-hidden="true"
        @change="onPhotos"
      />
      <form class="max-composer__row" @submit.prevent="send()">
        <button
          type="button"
          class="max-menu"
          :class="{ 'max-menu--on': quickOpen }"
          :aria-expanded="quickOpen"
          aria-label="Меню бота: готовые команды"
          @click="quickOpen = !quickOpen"
        >
          <v-icon icon="mdi-view-grid" size="22" />
        </button>
        <v-textarea
          v-model="text"
          placeholder="Сообщение"
          rows="1"
          auto-grow
          max-rows="4"
          variant="plain"
          density="compact"
          hide-details
          aria-label="Текст сообщения"
          class="max-input"
          @keydown.enter.exact.prevent="send()"
        />
        <v-btn
          icon="mdi-paperclip"
          variant="text"
          size="large"
          :disabled="chatId === null || photos.length >= MAX_PHOTOS"
          aria-label="Приложить фото"
          class="max-icon"
          @click="fileInput?.click()"
        />
        <v-btn
          type="submit"
          icon="mdi-send"
          variant="text"
          size="large"
          :loading="sending"
          :disabled="(!text.trim() && !photos.length) || chatId === null"
          aria-label="Отправить"
          class="max-icon max-icon--send"
        />
      </form>
    </footer>
  </div>
</template>

<style scoped>
/*
 * Скин MAX: эмулятор повторяет чужой интерфейс, поэтому цвета здесь свои, а не из темы
 * приложения. Светлый фон с узором, белые пузыри, синие кнопки под сообщением.
 */
.max-screen {
  --mx-bg: #bedcf6;
  --mx-doodle: 0.5;
  --mx-surface: #ffffff;
  --mx-ink: #121417;
  --mx-sub: #56657a;
  --mx-in: #ffffff;
  --mx-out: #dcebfa;
  --mx-time: rgba(18, 20, 23, 0.62);
  --mx-key: #2a6fca;
  --mx-key-ink: #ffffff;
  --mx-pill: rgba(28, 78, 138, 0.78);
  --mx-accent: #2b7ce1;
  --mx-line: rgba(18, 20, 23, 0.08);
  position: fixed;
  inset: 0;
  z-index: 5;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: var(--app-max-width);
  margin: 0 auto;
  color: var(--mx-ink);
  background: var(--mx-surface);
}
.v-theme--dark .max-screen {
  --mx-bg: #0f1b2a;
  --mx-doodle: 0.1;
  --mx-surface: #182533;
  --mx-ink: #f2f5f9;
  --mx-sub: #94a3b8;
  --mx-in: #1e2c3d;
  --mx-out: #2b4a6f;
  --mx-time: rgba(242, 245, 249, 0.66);
  --mx-pill: rgba(0, 0, 0, 0.45);
  --mx-line: rgba(255, 255, 255, 0.1);
}

.max-header {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 60px;
  padding: calc(env(safe-area-inset-top) + 4px) 6px 4px 2px;
  background: var(--mx-surface);
  border-bottom: 1px solid var(--mx-line);
}
.max-header__avatar {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: 50%;
  object-fit: cover;
}
.max-header__avatar--group {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  background: var(--mx-accent);
}
.max-header__name {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.2;
}
.max-header__check {
  color: var(--mx-accent);
}
.max-header__sub {
  font-size: 14px;
  color: var(--mx-sub);
}
.max-error {
  flex: 1;
}

/* Лента: узор из звёзд, планет и самолётиков белыми линиями, как обои чата в MAX */
.max-chat {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  background-color: var(--mx-bg);
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220' viewBox='0 0 220 220' fill='none' stroke='white' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'><path d='M30 24l3 7 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z'/><circle cx='120' cy='40' r='9'/><ellipse cx='120' cy='40' rx='17' ry='5' transform='rotate(-20 120 40)'/><path d='M176 28l-26 10 10 5 3 10z'/><path d='M60 104c0-4 3-7 7-7s7 3 7 7c0 7-7 9-7 14-0-5-7-7-7-14z'/><path d='M150 110h26c5 0 8 3 8 8v10c0 5-3 8-8 8h-14l-9 7v-7c-5 0-3-3-3-8v-10c0-5 3-8 0-8z'/><circle cx='40' cy='170' r='2'/><circle cx='190' cy='172' r='2'/><circle cx='100' cy='190' r='2'/><path d='M112 150l2 5 5 1-4 3 1 5-4-2-4 2 1-5-4-3 5-1z'/><path d='M24 136c6-6 14-6 20 0'/><path d='M170 70c0-6 5-10 11-10s11 4 11 10'/></svg>");
  background-size: 220px 220px;
  background-repeat: repeat;
}
.v-theme--dark .max-chat {
  background-blend-mode: soft-light;
}
.max-chat__inner {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 10px 14px;
}
.max-sys {
  align-self: center;
  width: fit-content;
  margin: 4px auto;
  padding: 3px 10px;
  border-radius: 10px;
  background: var(--mx-pill);
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  text-align: center;
}
.max-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  max-width: 100%;
}
.max-row--out {
  flex-direction: row-reverse;
}
.max-avatar {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 50%;
  object-fit: cover;
}
.max-avatar--letter {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #caf0f8;
  font-weight: 700;
  font-size: 14px;
}
.max-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 84%;
  min-width: 0;
}
.max-row--out .max-col {
  align-items: flex-end;
}
.max-msg {
  padding: 7px 10px 6px 12px;
  border-radius: 16px;
  background: var(--mx-in);
  color: var(--mx-ink);
  font-size: 15.5px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}
.max-msg--out {
  background: var(--mx-out);
}
.max-msg--photo {
  padding-top: 4px;
}
.max-msg--deleted {
  font-style: italic;
  color: var(--mx-sub);
}
.max-msg__name {
  margin-bottom: 2px;
  font-size: 14px;
  font-weight: 700;
}
.max-msg__photos {
  display: flex;
  gap: 4px;
  margin: 0 -6px 6px -8px;
}
.max-msg__photos img {
  height: 160px;
  min-width: 0;
  flex: 1;
  border-radius: 12px;
  object-fit: cover;
}
/* время прижато к правому нижнему углу текста, как в мессенджере */
.max-msg__text::after {
  content: '';
  display: inline-block;
  width: 52px;
}
.max-msg__time {
  float: right;
  margin: 6px -4px -2px 6px;
  font-size: 14px;
  color: var(--mx-time);
  white-space: nowrap;
}
.max-notice {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 6px;
  font-size: 14px;
  color: var(--mx-sub);
}
.max-keys {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}
.max-keys__row {
  display: flex;
  gap: 4px;
}
.max-key {
  display: inline-flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 0;
  min-height: 44px;
  padding: 8px 12px;
  border: 0;
  border-radius: 12px;
  background: var(--mx-key);
  color: var(--mx-key-ink);
  font: inherit;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition:
    transform 0.12s ease,
    filter 0.12s ease;
}
.max-key:active {
  transform: scale(0.98);
  filter: brightness(0.92);
}
.max-key:disabled {
  opacity: 0.75;
  cursor: progress;
}
.max-key:focus-visible {
  outline: 3px solid var(--mx-ink);
  outline-offset: 2px;
}

.max-composer {
  padding: 0 0 calc(env(safe-area-inset-bottom) + 6px);
  background: var(--mx-surface);
  border-top: 1px solid var(--mx-line);
}
.max-composer__row {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  padding: 6px 6px 0 8px;
}
.max-menu {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  margin-bottom: 2px;
  border: 0;
  border-radius: 50%;
  background: var(--mx-accent);
  color: #ffffff;
  cursor: pointer;
  transition: transform 0.2s var(--ease-spring);
}
.max-menu--on {
  transform: rotate(90deg);
}
.max-menu:focus-visible {
  outline: 3px solid var(--mx-ink);
  outline-offset: 2px;
}
.max-input {
  flex: 1;
  margin: 0 4px;
  font-size: 16px;
}
.max-input :deep(.v-field__input) {
  padding-top: 11px;
  padding-bottom: 11px;
  color: var(--mx-ink);
  min-height: 44px;
}
.max-input :deep(.v-field__input::placeholder) {
  color: var(--mx-sub);
  opacity: 1;
}
.max-icon {
  color: var(--mx-sub) !important;
}
.max-icon--send:not(:disabled) {
  color: var(--mx-accent) !important;
}
.max-quick {
  gap: 6px;
  padding: 8px 10px 2px;
}
.max-quick__item {
  flex-shrink: 0;
  min-height: 36px;
  padding: 6px 12px;
  border: 1px solid var(--mx-line);
  border-radius: 999px;
  background: transparent;
  color: var(--mx-ink);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}
.max-quick__item:disabled {
  opacity: 0.5;
}
</style>
