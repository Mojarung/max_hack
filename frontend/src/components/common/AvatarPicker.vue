<script setup lang="ts">
import { computed, ref } from 'vue'
import { meApi } from '@/api/endpoints'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import { notify } from '@/lib/notify'
import { haptic } from '@/max/bridge'
import { useSessionStore } from '@/stores/session'
import { chosenPreset, PRESET_COUNT, presetAvatar } from '@/utils/avatar'

/** Выбор аватарки: одна из готовых картинок или своё фото. Меняет только аватар текущего жителя. */
const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{ changed: [] }>()
const session = useSessionStore()

const presets = Array.from({ length: PRESET_COUNT }, (_, i) => i + 1)
const avatar = computed(() => session.me?.user.avatar ?? null)
const current = computed(() => chosenPreset(avatar.value))
const busy = ref<number | 'upload' | 'reset' | null>(null)
const progress = ref(0)
const fileInput = ref<HTMLInputElement | null>(null)

async function apply(kind: number | 'upload' | 'reset', run: () => ReturnType<typeof meApi.me>) {
  if (busy.value) return
  busy.value = kind
  try {
    const me = await run()
    session.me = me
    haptic.notify('success')
    notify.success('Аватарка обновлена')
    emit('changed')
    open.value = false
  } catch (error) {
    notify.error(error, 'Не удалось сменить аватарку')
  } finally {
    busy.value = null
    progress.value = 0
  }
}

function pick(n: number): void {
  if (n === current.value) {
    open.value = false
    return
  }
  void apply(n, () => meApi.setAvatar(n))
}

function onFile(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  void apply('upload', () =>
    meApi.uploadAvatar(file, (f) => (progress.value = Math.round(f * 100))),
  )
}
</script>

<template>
  <Drawer v-model:open="open">
    <DrawerContent>
      <DrawerHeader title="Аватарка" description="Выберите картинку или поставьте своё фото" />
      <div class="presets" role="radiogroup" aria-label="Готовые аватарки">
        <button
          v-for="n in presets"
          :key="n"
          type="button"
          role="radio"
          class="preset"
          :class="{ 'preset--active': n === current }"
          :aria-checked="n === current"
          :aria-label="`Картинка ${n}`"
          :disabled="busy !== null"
          @click="pick(n)"
        >
          <img :src="presetAvatar(n)" alt="" width="88" height="88" loading="lazy" />
          <v-progress-circular
            v-if="busy === n"
            class="preset__spinner"
            indeterminate
            color="primary"
            size="36"
          />
          <v-icon
            v-else-if="n === current"
            class="preset__check"
            icon="mdi-check-circle"
            size="28"
          />
        </button>
      </div>

      <input
        ref="fileInput"
        type="file"
        accept="image/jpeg,image/png,image/webp,image/heic"
        class="sr-only"
        tabindex="-1"
        aria-hidden="true"
        @change="onFile"
      />
      <v-btn
        block
        size="large"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-image-plus-outline"
        class="mt-4"
        :loading="busy === 'upload'"
        :disabled="busy !== null && busy !== 'upload'"
        @click="fileInput?.click()"
      >
        {{ avatar === 'upload' ? 'Поставить другое фото' : 'Поставить своё фото' }}
        <template #loader>Загружаем... {{ progress }}%</template>
      </v-btn>
      <v-btn
        v-if="avatar"
        block
        size="large"
        variant="text"
        class="mt-1"
        :loading="busy === 'reset'"
        :disabled="busy !== null && busy !== 'reset'"
        @click="apply('reset', () => meApi.setAvatar(null))"
      >
        Вернуть как было
      </v-btn>
    </DrawerContent>
  </Drawer>
</template>

<style scoped>
.presets {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 4px;
}
.preset {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 1;
  padding: 8px;
  border: 0;
  border-radius: var(--r-lg);
  background: rgba(var(--v-theme-on-surface), 0.05);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition:
    transform 0.3s var(--ease-spring),
    background-color 0.2s ease,
    box-shadow 0.2s ease;
}
.preset img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.preset:active {
  transform: scale(0.94);
  transition-duration: 0.1s;
}
.preset--active {
  background: rgba(var(--v-theme-primary), 0.12);
  box-shadow: inset 0 0 0 3px rgb(var(--v-theme-primary));
}
.preset:focus-visible {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
.preset__check {
  position: absolute;
  right: 6px;
  bottom: 6px;
  color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-surface));
  border-radius: 50%;
}
.preset__spinner {
  position: absolute;
}
</style>
