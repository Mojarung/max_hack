<script setup lang="ts">
import { computed } from 'vue'
import { openLink } from '@/max/bridge'
import { useSessionStore } from '@/stores/session'
import { orgTitleCap, plural } from '@/utils/format'

const session = useSessionStore()
const house = computed(() => session.me?.house)

const links = computed(() => [
  {
    to: '/announcements',
    title: 'Объявления',
    subtitle: 'Отключения, работы, собрания',
    icon: 'mdi-bullhorn-variant-outline',
  },
  {
    to: '/more/documents',
    title: 'Документы',
    subtitle: 'Документы дома и ваши личные',
    icon: 'mdi-file-document-multiple-outline',
  },
  {
    to: '/people',
    title: 'Соседи',
    subtitle: house.value
      ? `${house.value.members_count} ${plural(house.value.members_count, ['участник', 'участника', 'участников'])} чата`
      : 'Кто живёт рядом',
    icon: 'mdi-account-group-outline',
  },
])

function call(phone: string): void {
  openLink(`tel:${phone.replace(/[^\d+]/g, '')}`)
}
function mail(email: string): void {
  openLink(`mailto:${email}`)
}
</script>

<template>
  <div v-if="house" class="page">
    <section class="card-soft p-4">
      <div class="flex items-start gap-3">
        <v-icon icon="mdi-home-city-outline" size="32" color="primary" aria-hidden="true" />
        <div class="min-w-0 flex-1">
          <h2 class="m-0 text-lg leading-snug font-bold">{{ house.title }}</h2>
          <p class="text-muted m-0 mt-1">{{ house.address || 'Адрес ещё не указан' }}</p>
        </div>
      </div>
      <p v-if="house.info" class="info mt-3 mb-0">{{ house.info }}</p>
      <p v-else class="text-muted mt-3 mb-0 text-sm">
        Администратор ещё не добавил информацию о доме: диспетчерскую, председателя, правила.
      </p>
    </section>

    <h2 class="section-title">Кто обслуживает дом</h2>
    <section class="card-soft p-4">
      <div class="text-lg leading-snug font-semibold">
        {{ orgTitleCap(house.uk_name) || 'Управляющая компания не указана' }}
      </div>
      <div v-if="house.uk_phone" class="text-muted mt-1 tabular-nums">{{ house.uk_phone }}</div>
      <!-- Одно главное действие - позвонить; почта второстепенна -->
      <v-btn
        v-if="house.uk_phone"
        block
        size="x-large"
        color="primary"
        class="mt-3"
        prepend-icon="mdi-phone-outline"
        @click="call(house.uk_phone)"
      >
        Позвонить
      </v-btn>
      <v-btn
        v-if="house.uk_email"
        block
        size="large"
        variant="text"
        color="primary"
        class="mt-1"
        prepend-icon="mdi-email-outline"
        @click="mail(house.uk_email)"
      >
        Написать на почту
      </v-btn>
      <p class="text-muted mt-3 mb-0 text-sm">
        Когда соседи наберут голоса, Кузя сам отправит сюда обращение.
        <template v-if="session.isAdmin">
          Сейчас тестовый режим: письма уходят на проверочный адрес.</template
        >
      </p>
    </section>

    <nav class="mt-3 flex flex-col gap-2" aria-label="Разделы дома">
      <router-link
        v-for="l in links"
        :key="l.to"
        :to="l.to"
        class="card-soft tap-card flex items-center gap-3 p-3 text-inherit no-underline"
      >
        <v-avatar color="primary" variant="tonal" size="48" rounded="lg">
          <v-icon :icon="l.icon" size="26" />
        </v-avatar>
        <div class="min-w-0 flex-1">
          <div class="text-base font-semibold">{{ l.title }}</div>
          <div class="text-muted text-sm">{{ l.subtitle }}</div>
        </div>
        <v-icon icon="mdi-chevron-right" />
      </router-link>
    </nav>

    <v-btn
      v-if="session.isAdmin"
      to="/more/house/edit"
      block
      size="x-large"
      color="primary"
      variant="tonal"
      class="mt-4"
      prepend-icon="mdi-home-edit-outline"
    >
      Редактировать дом
    </v-btn>
  </div>
</template>

<style scoped>
.info {
  white-space: pre-line;
  line-height: 1.5;
}
</style>
