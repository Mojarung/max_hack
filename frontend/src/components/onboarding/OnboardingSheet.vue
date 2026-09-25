<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import KuzyaMascot from '@/components/kuzya/KuzyaMascot.vue'
import type { KuzyaMood } from '@/components/kuzya/geometry'
import { DrawerDescription, DrawerTitle } from 'vaul-vue'
import { Drawer, DrawerContent } from '@/components/ui/drawer'
import { haptic } from '@/max/bridge'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const step = ref(0)
const open = computed({
  get: () => session.needsOnboarding,
  set: (value: boolean) => {
    if (!value) void session.completeOnboarding()
  },
})

interface Step {
  mood: KuzyaMood
  title: string
  text: string
  points?: { icon: string; text: string }[]
}

const steps = computed<Step[]>(() => {
  const bot = session.me?.bot_username
  const list: Step[] = [
    {
      mood: 'happy',
      title: `Привет! Я Кузя, домовой ${session.me?.house.title ? `дома «${session.me.house.title}»` : 'вашего дома'}`,
      text: 'Помогаю соседям договариваться и добиваться, чтобы поломки чинили в срок.',
    },
    {
      mood: 'worried',
      title: 'Что-то сломалось? Сфотографируйте',
      text: 'Три шага, и обращение уйдёт тем, кто отвечает за ремонт:',
      points: [
        { icon: 'mdi-camera-outline', text: 'Фото и пара слов о проблеме' },
        { icon: 'mdi-thumb-up-outline', text: 'Соседи поддерживают голосом в чате или здесь' },
        { icon: 'mdi-email-fast-outline', text: 'Я отправляю обращение и слежу за сроком' },
      ],
    },
    {
      mood: 'proud',
      title: 'Всё о доме в одном месте',
      text: 'Внизу экрана разделы, а во вкладке «Ещё»:',
      points: [
        { icon: 'mdi-bullhorn-variant-outline', text: 'Объявления: отключения, работы, собрания' },
        { icon: 'mdi-file-document-multiple-outline', text: 'Документы дома и ваши личные' },
        { icon: 'mdi-account-group-outline', text: 'Соседи, события и барахолка' },
        { icon: 'mdi-shield-home-outline', text: 'Укрытия рядом на случай тревоги' },
      ],
    },
    {
      mood: 'ok',
      title: 'Зовите меня в чате дома',
      text: bot
        ? `Напишите «Кузя, …» или упомяните @${bot}: «Кузя, сделай объявление о субботнике в субботу в 11».`
        : 'Напишите «Кузя, …»: например, «Кузя, сделай объявление о субботнике в субботу в 11».',
    },
  ]
  if (session.needsSetup) {
    list.push({
      mood: 'proud',
      title: 'Вы администратор дома',
      text: 'Укажите адрес и управляющую компанию: так я найду укрытия рядом и буду знать, кому писать обращения.',
    })
  }
  return list
})
const current = computed(() => steps.value[Math.min(step.value, steps.value.length - 1)]!)
const last = computed(() => step.value >= steps.value.length - 1)

function next(): void {
  haptic.selection()
  if (!last.value) {
    step.value += 1
    return
  }
  const goSetup = session.needsSetup
  void session.completeOnboarding()
  if (goSetup) void router.push('/more/house/edit')
}
</script>

<template>
  <Drawer v-model:open="open">
    <DrawerContent>
      <section class="flex flex-col items-center pt-2 text-center" aria-live="polite">
        <KuzyaMascot :mood="current.mood" :size="120" :interactive="false" />
        <DrawerTitle as="h2" class="mt-3 mb-2 text-xl leading-snug font-bold">{{
          current.title
        }}</DrawerTitle>
        <DrawerDescription class="text-muted m-0 max-w-[420px]">{{
          current.text
        }}</DrawerDescription>
        <ul
          v-if="current.points"
          class="mt-3 mb-0 flex w-full list-none flex-col gap-2 p-0 text-left"
        >
          <li
            v-for="p in current.points"
            :key="p.text"
            class="card-soft flex items-center gap-3 p-3"
          >
            <v-icon :icon="p.icon" color="primary" size="26" aria-hidden="true" />
            <span>{{ p.text }}</span>
          </li>
        </ul>
      </section>

      <div class="mt-4 flex justify-center gap-2" aria-hidden="true">
        <span v-for="(_, i) in steps" :key="i" class="dot" :class="{ 'dot--active': i === step }" />
      </div>
      <p class="sr-only">Шаг {{ step + 1 }} из {{ steps.length }}</p>

      <v-btn block size="x-large" color="primary" class="mt-4" @click="next">
        {{ last ? (session.needsSetup ? 'Настроить дом' : 'Начать') : 'Дальше' }}
      </v-btn>
      <v-btn
        v-if="!last"
        block
        size="large"
        variant="text"
        class="mt-1"
        @click="session.completeOnboarding()"
      >
        Пропустить
      </v-btn>
    </DrawerContent>
  </Drawer>
</template>

<style scoped>
.dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.25);
  transition: width 0.2s ease;
}
.dot--active {
  width: 24px;
  background: rgb(var(--v-theme-primary));
}
</style>
