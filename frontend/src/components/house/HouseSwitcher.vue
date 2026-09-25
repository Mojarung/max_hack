<script setup lang="ts">
import { computed, ref } from 'vue'
import { Drawer, DrawerContent, DrawerHeader } from '@/components/ui/drawer'
import { haptic } from '@/max/bridge'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import { plural } from '@/utils/format'

const session = useSessionStore()
const open = ref(false)
const switching = ref<number | null>(null)

const title = computed(() => session.me?.house.title ?? 'Домовой Кузя')

async function pick(id: number): Promise<void> {
  haptic.selection()
  switching.value = id
  await session.switchHouse(id)
  switching.value = null
  open.value = false
}

async function refresh(): Promise<void> {
  const before = session.houses.length
  try {
    await session.loadHouses(true)
    const added = session.houses.length - before
    notify.success(
      added > 0
        ? `Нашёл ещё ${added} ${plural(added, ['дом', 'дома', 'домов'])}`
        : 'Новых домов не нашлось',
      added > 0 ? undefined : 'Кузя видит только чаты, куда его добавили',
    )
  } catch (e) {
    notify.error(e, 'Не удалось проверить чаты')
  }
}
</script>

<template>
  <slot name="trigger" :open="() => (open = true)">
    <button
      type="button"
      class="switcher"
      :aria-label="`Дом: ${title}. Выбрать другой дом`"
      aria-haspopup="dialog"
      @click="open = true"
    >
      <span class="switcher__title">{{ title }}</span>
      <v-icon icon="mdi-chevron-down" size="22" aria-hidden="true" />
    </button>
  </slot>

  <Drawer v-model:open="open">
    <DrawerContent>
      <DrawerHeader
        title="Ваши дома"
        description="Дома появляются сами из чатов, где вы состоите вместе с Кузей"
      />
      <ul class="m-0 flex list-none flex-col gap-2 p-0" aria-label="Список домов">
        <li v-for="h in session.houses" :key="h.id">
          <button
            type="button"
            class="house-row card-soft"
            :class="{ 'house-row--current': h.is_current }"
            :aria-current="h.is_current ? 'true' : undefined"
            :disabled="switching !== null"
            @click="pick(h.id)"
          >
            <v-icon
              :icon="h.is_current ? 'mdi-home-circle' : 'mdi-home-outline'"
              size="28"
              color="primary"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1 text-left">
              <span class="block truncate font-semibold">{{ h.title }}</span>
              <span class="text-muted block truncate text-sm">
                {{ h.address || 'Адрес ещё не указан' }}
                <template v-if="h.role === 'admin'"> · вы администратор</template>
              </span>
            </span>
            <v-progress-circular
              v-if="switching === h.id"
              indeterminate
              size="22"
              width="2"
              color="primary"
            />
            <v-icon v-else-if="h.is_current" icon="mdi-check" color="primary" aria-hidden="true" />
          </button>
        </li>
      </ul>
      <v-btn
        block
        size="large"
        variant="tonal"
        color="primary"
        class="mt-3"
        prepend-icon="mdi-refresh"
        :loading="session.housesLoading"
        @click="refresh"
      >
        Найти мои дома
      </v-btn>
      <p class="text-muted mt-3 mb-0 text-sm">
        Нет нужного дома? Попросите администратора домового чата добавить Кузю в чат.
      </p>
    </DrawerContent>
  </Drawer>
</template>

<style scoped>
.switcher {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 48px;
  align-items: center;
  gap: 2px;
  padding: 0 4px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: inherit;
  font-size: 1.125rem;
  font-weight: 700;
  line-height: 1.2;
}
.switcher:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
}
.switcher__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.house-row {
  display: flex;
  width: 100%;
  min-height: 64px;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  color: inherit;
  text-align: left;
}
.house-row--current {
  outline: 2px solid rgb(var(--v-theme-primary));
}
</style>
