<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { houseApi } from '@/api/endpoints'
import type { GeoResult, HouseIn } from '@/api/types'
import { useDirtyGuard } from '@/composables/useDirtyGuard'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import { plural } from '@/utils/format'

const session = useSessionStore()
const router = useRouter()
const house = session.me!.house

const form = reactive({
  title: house.title,
  address: house.address,
  lat: house.lat,
  lon: house.lon,
  info: house.info ?? '',
  uk_name: house.uk_name ?? '',
  uk_email: house.uk_email ?? '',
  uk_phone: house.uk_phone ?? '',
  vote_threshold_pct: house.vote_threshold_pct,
})
const initial = JSON.stringify(form)
const dirty = computed(() => JSON.stringify(form) !== initial)
useDirtyGuard(dirty)

const saving = ref(false)
const geoLoading = ref(false)
const geoResults = ref<GeoResult[]>([])
const syncing = ref(false)
const botIsAdmin = ref(house.bot_is_admin ?? null)

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const rules = {
  title: (v: string) => v.trim().length >= 3 || 'Хотя бы 3 символа',
  address: (v: string) => v.trim().length >= 5 || 'Укажите улицу и номер дома',
  email: (v: string) => !v.trim() || EMAIL_RE.test(v.trim()) || 'Проверьте адрес почты',
}
const valid = computed(
  () =>
    rules.title(form.title) === true &&
    rules.address(form.address) === true &&
    rules.email(form.uk_email) === true,
)
const votesHint = computed(() => {
  const n = Math.max(3, Math.ceil((house.members_count * form.vote_threshold_pct) / 100))
  return `${n} ${plural(n, ['голос', 'голоса', 'голосов'])} из ${house.members_count} участников чата`
})

async function findAddress(): Promise<void> {
  geoLoading.value = true
  try {
    geoResults.value = await houseApi.geocode(form.address)
    if (!geoResults.value.length)
      notify.info('Адрес не нашёлся', 'Попробуйте указать город и улицу')
  } catch (e) {
    notify.error(e)
  } finally {
    geoLoading.value = false
  }
}

function pickGeo(r: GeoResult): void {
  form.lat = r.lat
  form.lon = r.lon
  geoResults.value = []
  notify.success('Координаты дома заданы', 'Кузя покажет ближайшие укрытия')
}

async function sync(): Promise<void> {
  syncing.value = true
  try {
    const res = await houseApi.sync()
    botIsAdmin.value = res.bot_is_admin
    notify.success(
      res.members
        ? `Сверил ${res.members} ${plural(res.members, ['участника', 'участников', 'участников'])}`
        : 'Список участников недоступен',
      res.members
        ? 'Администраторы чата стали администраторами дома'
        : 'Сделайте Кузю администратором чата',
    )
    await session.refreshMe()
  } catch (e) {
    notify.error(e, 'Не удалось сверить с чатом')
  } finally {
    syncing.value = false
  }
}

async function save(): Promise<void> {
  if (!valid.value) return
  saving.value = true
  const body: HouseIn = {
    title: form.title.trim(),
    address: form.address.trim(),
    lat: form.lat,
    lon: form.lon,
    info: form.info.trim(),
    uk_email: form.uk_email.trim() || null,
    uk_phone: form.uk_phone.trim() || null,
    vote_threshold_pct: form.vote_threshold_pct,
    setup_done: true,
  }
  if (form.uk_name.trim().length >= 3) body.uk_name = form.uk_name.trim()
  try {
    session.me = await houseApi.update(body)
    notify.success('Дом сохранён', 'Жители видят обновлённую информацию')
    await router.replace('/more/house')
  } catch (e) {
    notify.error(e, 'Не удалось сохранить')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="!session.isAdmin" class="page">
    <p class="mt-0">
      Настройки дома меняет администратор чата. Посмотреть информацию можно в разделе «О доме».
    </p>
    <v-btn to="/more/house" color="primary" size="large">О доме</v-btn>
  </div>
  <div v-else class="page">
    <p v-if="!house.setup_done" class="text-muted mt-0 mb-3">
      Кузя подключился к чату дома. Заполните адрес и управляющую компанию: без них не найти
      ближайшие укрытия и некому отправить обращение.
    </p>

    <form class="flex flex-col gap-3" @submit.prevent="save">
      <h2 class="section-title !mt-0">Дом</h2>
      <v-text-field v-model="form.title" label="Название" :rules="[rules.title]" maxlength="256" />
      <v-text-field
        v-model="form.address"
        label="Адрес"
        placeholder="Казань, ул. Чистопольская, 5"
        :rules="[rules.address]"
        maxlength="512"
      />
      <v-btn
        variant="tonal"
        color="primary"
        size="large"
        prepend-icon="mdi-map-search-outline"
        :loading="geoLoading"
        :disabled="rules.address(form.address) !== true"
        @click="findAddress"
      >
        Найти дом на карте
      </v-btn>
      <v-list v-if="geoResults.length" class="card-soft py-0" aria-label="Найденные адреса">
        <v-list-item
          v-for="r in geoResults"
          :key="`${r.lat},${r.lon}`"
          prepend-icon="mdi-map-marker-outline"
          class="py-2"
          @click="pickGeo(r)"
        >
          <span class="block leading-snug whitespace-normal">{{ r.title }}</span>
        </v-list-item>
      </v-list>
      <p class="text-muted m-0 text-sm">
        <v-icon icon="mdi-crosshairs-gps" size="18" aria-hidden="true" />
        Координаты: {{ form.lat.toFixed(5) }}, {{ form.lon.toFixed(5) }}
      </p>

      <v-textarea
        v-model="form.info"
        label="Информация для жителей"
        placeholder="Диспетчерская, председатель совета дома, вывоз крупногабарита, правила"
        rows="4"
        auto-grow
        maxlength="4000"
      />

      <h2 class="section-title">Управляющая компания</h2>
      <v-text-field v-model="form.uk_name" label="Название УК" maxlength="256" />
      <v-text-field
        v-model="form.uk_email"
        label="E-mail для обращений"
        type="email"
        inputmode="email"
        :rules="[rules.email]"
      />
      <v-text-field
        v-model="form.uk_phone"
        label="Телефон диспетчерской"
        type="tel"
        inputmode="tel"
      />
      <p class="text-muted m-0 text-sm">
        Пока это модельная интеграция: обращение уходит на тестовый адрес, а не в УК.
      </p>

      <h2 class="section-title">Голосование</h2>
      <div>
        <div class="flex items-baseline justify-between">
          <label for="threshold" class="font-semibold">Порог для обращения</label>
          <span class="font-bold tabular-nums">{{ form.vote_threshold_pct }}%</span>
        </div>
        <v-slider
          id="threshold"
          v-model="form.vote_threshold_pct"
          :min="5"
          :max="100"
          :step="5"
          color="primary"
          hide-details
          aria-label="Порог голосов в процентах"
        />
        <p class="text-muted m-0 text-sm">Сейчас это {{ votesHint }}</p>
      </div>

      <v-btn
        type="submit"
        block
        size="x-large"
        color="primary"
        class="sticky-cta mt-2"
        :disabled="!valid"
        :loading="saving"
        prepend-icon="mdi-content-save-outline"
      >
        Сохранить
      </v-btn>
    </form>

    <template v-if="house.has_chat && !house.is_demo">
      <h2 class="section-title">Чат дома</h2>
      <section class="card-soft p-4">
        <p class="m-0">
          <v-icon
            :icon="botIsAdmin ? 'mdi-shield-check-outline' : 'mdi-shield-alert-outline'"
            color="primary"
            aria-hidden="true"
          />
          {{
            botIsAdmin
              ? 'Кузя - администратор чата: убирает спам и знает соседей.'
              : 'Кузя не администратор чата: не сможет удалять спам и проверять участников. Назначьте его администратором в настройках чата MAX.'
          }}
        </p>
        <p class="text-muted mt-2 mb-3 text-sm">
          Администраторы чата MAX автоматически становятся администраторами дома, а вышедшие из чата
          теряют доступ к дому.
        </p>
        <v-btn
          block
          variant="tonal"
          color="primary"
          size="large"
          prepend-icon="mdi-account-sync-outline"
          :loading="syncing"
          @click="sync"
        >
          Сверить жителей с чатом
        </v-btn>
      </section>
    </template>
  </div>
</template>
