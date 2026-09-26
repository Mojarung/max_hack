<script setup lang="ts">
import { ref } from 'vue'
import { useSessionStore } from '@/stores/session'
import { fullName } from '@/utils/format'

const session = useSessionStore()
const switching = ref(false)

async function pick(id: number): Promise<void> {
  switching.value = true
  try {
    await session.switchUser(id)
  } finally {
    switching.value = false
  }
}
</script>

<template>
  <v-menu location="bottom end" max-height="70dvh">
    <template #activator="{ props: activator }">
      <!-- кнопка, а не чип: тач-зона 44px и aria-expanded меню допустимы только у button -->
      <v-btn
        v-bind="activator"
        size="large"
        variant="tonal"
        color="secondary"
        class="demo-switch"
        prepend-icon="mdi-account-switch-outline"
        append-icon="mdi-chevron-down"
        :loading="switching"
        :aria-label="`Демо-режим. Сейчас: ${session.currentDevUser?.first_name ?? 'житель'}. Сменить жителя`"
      >
        Демо: {{ session.currentDevUser?.first_name ?? '...' }}
      </v-btn>
    </template>
    <v-list density="comfortable" min-width="250" nav>
      <v-list-subheader>Войти как житель (демо)</v-list-subheader>
      <v-list-item
        v-for="u in session.devUsers"
        :key="u.max_user_id"
        :active="u.max_user_id === session.devUserId"
        color="primary"
        :title="fullName(u)"
        :subtitle="
          [u.apartment ? `кв. ${u.apartment}` : null, u.role === 'admin' ? 'администратор' : null]
            .filter(Boolean)
            .join(' · ')
        "
        @click="pick(u.max_user_id)"
      >
        <template #append>
          <v-icon v-if="u.max_user_id === session.devUserId" icon="mdi-check" color="primary" />
        </template>
      </v-list-item>
    </v-list>
  </v-menu>
</template>

<style scoped>
.demo-switch {
  padding-inline: 10px;
  font-size: 0.875rem;
  letter-spacing: normal;
  text-transform: none;
}
</style>
