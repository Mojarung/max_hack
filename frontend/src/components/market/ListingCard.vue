<script setup lang="ts">
import type { ListingOut } from '@/api/types'
import PhotoCarousel from '@/components/common/PhotoCarousel.vue'
import { formatPrice } from '@/utils/format'
import { LISTING_CATEGORY_ICONS, LISTING_STATUS_META } from '@/utils/labels'

defineProps<{ listing: ListingOut }>()
</script>

<template>
  <router-link
    :to="`/market/${listing.id}`"
    class="card-soft tap-card flex flex-col overflow-hidden text-inherit no-underline"
    :aria-label="`${listing.title}, ${formatPrice(listing.price, listing.is_free)}`"
  >
    <div class="relative aspect-square w-full overflow-hidden bg-surface-variant">
      <!-- несколько фото листаются прямо в карточке, нажатие открывает объявление.
           Для диктора и клавиатуры карточка - одна ссылка с подписью, все фото есть на экране вещи -->
      <PhotoCarousel :photos="listing.photos" :alt="listing.title" aria-hidden="true">
        <v-icon
          :icon="LISTING_CATEGORY_ICONS[listing.category] ?? 'mdi-shape-outline'"
          size="44"
          color="primary"
        />
      </PhotoCarousel>
      <v-chip
        v-if="listing.status !== 'active'"
        class="!absolute top-2 right-2"
        :color="LISTING_STATUS_META[listing.status].color"
        variant="flat"
        size="small"
        :prepend-icon="LISTING_STATUS_META[listing.status].icon"
      >
        {{ LISTING_STATUS_META[listing.status].title }}
      </v-chip>
    </div>
    <div class="flex flex-1 flex-col p-3">
      <div class="flex items-center gap-1 text-lg leading-tight font-bold">
        <v-icon v-if="listing.is_free" icon="mdi-gift-outline" size="20" />
        {{ formatPrice(listing.price, listing.is_free) }}
      </div>
      <h3 class="line-clamp-2 mt-1 mb-0 text-[15px] leading-snug font-medium">
        {{ listing.title }}
      </h3>
      <div class="text-muted mt-auto pt-1 text-sm">
        {{ listing.category_title
        }}<span v-if="listing.author?.apartment"> · кв. {{ listing.author.apartment }}</span>
      </div>
    </div>
  </router-link>
</template>
