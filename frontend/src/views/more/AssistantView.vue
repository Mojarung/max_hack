<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import { staggerIn } from '@/composables/useMotion'
import { useAssistantStore } from '@/stores/chat'
import { ASSISTANT_TOOL_TITLES } from '@/utils/labels'

const store = useAssistantStore()
const text = ref('')
const box = ref<HTMLElement | null>(null)

const SUGGESTIONS = [
  'Какие проблемы сейчас в доме?',
  'Когда ближайший субботник?',
  'Кто отвечает за лифт?',
  'Где ближайшее укрытие?',
  'Что отдают даром?',
]

function toolTitle(name: string): string {
  return ASSISTANT_TOOL_TITLES[name] ?? name
}

async function scrollDown(): Promise<void> {
  await nextTick()
  staggerIn(box.value, '[data-msg]')
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
}

watch(() => [store.messages.length, store.typing], scrollDown)

async function send(value?: string): Promise<void> {
  const message = (value ?? text.value).trim()
  if (!message || store.typing) return
  text.value = ''
  await store.send(message)
}
</script>

<template>
  <div class="page chat-page">
    <div v-if="!store.messages.length" class="flex flex-col items-center py-4 text-center">
      <KuzyaMascot mood="happy" :size="120" />
      <h2 class="mt-3 mb-1 text-lg font-bold">Привет! Я Кузя, домовой вашего дома</h2>
      <p class="text-muted m-0 max-w-[320px]">
        Спросите про проблемы, события, соседскую барахолку или укрытия. Я посмотрю и отвечу.
      </p>
    </div>

    <div ref="box" class="flex flex-col gap-2" aria-live="polite">
      <div
        v-for="m in store.messages"
        :key="m.id"
        data-msg
        class="flex items-end gap-2"
        :class="m.role === 'user' ? 'flex-row-reverse' : ''"
      >
        <img
          v-if="m.role === 'bot'"
          src="/kuzya-avatar.svg"
          alt=""
          width="32"
          height="32"
          class="shrink-0 rounded-full"
        />
        <div
          class="msg"
          :class="[m.role === 'user' ? 'msg--me' : 'msg--bot', { 'msg--failed': m.failed }]"
        >
          <div class="pre-wrap">{{ m.text }}</div>
          <div v-if="m.tools.length" class="mt-1.5 flex flex-wrap gap-1">
            <v-chip
              v-for="t in m.tools"
              :key="t"
              size="x-small"
              variant="tonal"
              prepend-icon="mdi-magnify"
            >
              смотрел {{ toolTitle(t) }}
            </v-chip>
          </div>
        </div>
      </div>
      <div v-if="store.typing" class="flex items-end gap-2" role="status">
        <img src="/kuzya-avatar.svg" alt="" width="32" height="32" class="shrink-0 rounded-full" />
        <div class="msg msg--bot">
          <span class="typing" aria-hidden="true"><i /><i /><i /></span>
          <span class="sr-only">Кузя печатает</span>
        </div>
      </div>
    </div>

    <div class="composer-wrap">
      <div class="chips-scroll mb-2">
        <v-chip
          v-for="s in SUGGESTIONS"
          :key="s"
          size="small"
          variant="outlined"
          :disabled="store.typing"
          @click="send(s)"
        >
          {{ s }}
        </v-chip>
      </div>
      <form class="flex items-end gap-2" @submit.prevent="send()">
        <v-textarea
          v-model="text"
          placeholder="Спросите Кузю"
          rows="1"
          auto-grow
          max-rows="4"
          density="comfortable"
          hide-details
          maxlength="1000"
          aria-label="Сообщение Кузе"
          class="flex-1"
          @keydown.enter.exact.prevent="send()"
        />
        <v-btn
          type="submit"
          icon="mdi-send"
          color="primary"
          size="large"
          :loading="store.typing"
          :disabled="!text.trim()"
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
.msg {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: 18px;
  font-size: 16px;
  line-height: 1.4;
}
.msg--bot {
  border-bottom-left-radius: 4px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), 0.1);
}
.msg--me {
  border-bottom-right-radius: 4px;
  color: rgb(var(--v-theme-on-primary));
  background: rgb(var(--v-theme-primary));
}
.msg--failed {
  border-color: rgba(var(--v-theme-error), 0.5);
  color: rgb(var(--v-theme-error));
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
.typing {
  display: inline-flex;
  gap: 4px;
  padding: 4px 0;
}
.typing i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.45);
  animation: typing 1.2s infinite ease-in-out;
}
.typing i:nth-child(2) {
  animation-delay: 0.15s;
}
.typing i:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes typing {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.5;
  }
  30% {
    transform: translateY(-5px);
    opacity: 1;
  }
}
</style>
