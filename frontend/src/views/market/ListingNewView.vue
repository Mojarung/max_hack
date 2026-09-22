<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listingsApi } from '@/api/endpoints'
import PhotoPicker from '@/components/common/PhotoPicker.vue'
import { useDirtyGuard } from '@/composables/useDirtyGuard'
import { notify } from '@/lib/notify'
import { useListingsStore } from '@/stores/listings'

const router = useRouter()
const store = useListingsStore()

const title = ref('')
const description = ref('')
const isFree = ref(false)
const price = ref<string>('')
const category = ref<string | null>(null)
const photos = ref<File[]>([])
const submitting = ref(false)
const progress = ref(0)
const done = ref(false)
const showErrors = ref(false)

const priceNumber = computed(() => Number(String(price.value).replace(/\s/g, '').replace(',', '.')))
const errors = computed(() => ({
  title: title.value.trim().length < 3 ? 'Напишите, что отдаёте или продаёте' : '',
  category: !category.value ? 'Выберите категорию' : '',
  price:
    !isFree.value && (!Number.isFinite(priceNumber.value) || priceNumber.value <= 0)
      ? 'Укажите цену или включите «Отдам даром»'
      : '',
}))
const valid = computed(() => !errors.value.title && !errors.value.category && !errors.value.price)
const dirty = computed(
  () => !done.value && (!!title.value || !!description.value || photos.value.length > 0),
)
useDirtyGuard(dirty)

onMounted(() => void store.loadCategories())

async function submit(): Promise<void> {
  showErrors.value = true
  if (!valid.value || submitting.value) {
    notify.warning('Проверьте поля формы')
    return
  }
  submitting.value = true
  progress.value = 0
  const form = new FormData()
  form.append('title', title.value.trim())
  form.append('description', description.value.trim())
  form.append('price', isFree.value ? '0' : String(Math.round(priceNumber.value)))
  form.append('category', category.value ?? 'other')
  photos.value.forEach((file) => form.append('photos', file, file.name))
  try {
    const listing = await listingsApi.create(form, (f) => (progress.value = Math.round(f * 100)))
    store.storeDetail(listing)
    done.value = true
    notify.success('Объявление опубликовано', 'Кузя расскажет о нём соседям')
    await router.replace(`/market/${listing.id}`)
  } catch (e) {
    notify.error(e, 'Не удалось опубликовать')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <section>
        <h2 class="mt-0 mb-2 text-base font-bold">Фото</h2>
        <PhotoPicker v-model="photos" />
      </section>

      <v-text-field
        v-model="title"
        label="Название"
        placeholder="Детская коляска"
        maxlength="100"
        :error-messages="showErrors ? errors.title : ''"
      />

      <v-select
        v-model="category"
        :items="store.categories"
        item-title="title"
        item-value="code"
        label="Категория"
        :error-messages="showErrors ? errors.category : ''"
      />

      <div class="card-soft px-4 py-2">
        <v-switch
          v-model="isFree"
          color="secondary"
          inset
          hide-details
          label="Отдам даром"
          density="comfortable"
        />
        <v-text-field
          v-if="!isFree"
          v-model="price"
          label="Цена, ₽"
          inputmode="numeric"
          placeholder="1500"
          class="mb-2"
          :error-messages="showErrors ? errors.price : ''"
        />
        <p v-else class="text-muted mt-0 mb-2 text-sm">
          Соседи увидят метку «Даром». Спасибо за доброе дело!
        </p>
      </div>

      <v-textarea
        v-model="description"
        label="Описание"
        placeholder="Состояние, размер, когда можно забрать"
        rows="3"
        auto-grow
        maxlength="2000"
        counter="2000"
      />

      <div v-if="submitting" aria-live="polite">
        <v-progress-linear :model-value="progress" color="primary" height="10" />
        <div class="text-muted mt-1 text-sm">Загружаем... {{ progress }}%</div>
      </div>

      <v-btn
        type="submit"
        block
        size="x-large"
        color="primary"
        prepend-icon="mdi-check"
        :loading="submitting"
      >
        Опубликовать
      </v-btn>
    </form>
  </div>
</template>
