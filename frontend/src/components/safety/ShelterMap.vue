<script setup lang="ts">
import 'leaflet/dist/leaflet.css'
import type * as Leaflet from 'leaflet'
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import type { ShelterOut } from '@/api/types'
import { formatDistance } from '@/utils/format'

const props = defineProps<{
  house: { lat: number; lon: number; title: string }
  shelters: ShelterOut[]
  me?: { lat: number; lon: number; source: 'gps' | 'house' } | null
  selectedId?: number | null
}>()
const emit = defineEmits<{ select: [id: number] }>()

const el = ref<HTMLElement | null>(null)
const failed = ref(false)
const L = shallowRef<typeof Leaflet | null>(null)
const map = shallowRef<Leaflet.Map | null>(null)
let layer: Leaflet.LayerGroup | null = null

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
}

function pin(lib: typeof Leaflet, icon: string, bg: string, size = 34): Leaflet.DivIcon {
  return lib.divIcon({
    className: 'kz-pin',
    html: `<span style="background:${bg};width:${size}px;height:${size}px"><i class="mdi ${icon}"></i></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

function render(): void {
  const lib = L.value
  const m = map.value
  if (!lib || !m) return
  layer?.remove()
  layer = lib.layerGroup().addTo(m)
  const points: [number, number][] = []

  lib
    .marker([props.house.lat, props.house.lon], {
      icon: pin(lib, 'mdi-home-heart', '#B8501A'),
      title: props.house.title,
    })
    .bindTooltip(escapeHtml(props.house.title))
    .addTo(layer)
  points.push([props.house.lat, props.house.lon])

  if (props.me && props.me.source === 'gps') {
    lib
      .circleMarker([props.me.lat, props.me.lon], {
        radius: 9,
        color: '#fff',
        weight: 3,
        fillColor: '#1E88E5',
        fillOpacity: 1,
      })
      .bindTooltip('Вы здесь')
      .addTo(layer)
    points.push([props.me.lat, props.me.lon])
  }

  props.shelters.forEach((s, i) => {
    const selected = s.id === props.selectedId
    const marker = lib
      .marker([s.lat, s.lon], {
        icon: pin(lib, 'mdi-shield-home', selected ? '#C62828' : '#00796B', selected ? 42 : 34),
        title: s.name,
        zIndexOffset: selected ? 1000 : 0,
      })
      .bindTooltip(
        `${escapeHtml(s.name)}${s.distance_m !== null ? ` · ${formatDistance(s.distance_m)}` : ''}`,
      )
      .on('click', () => emit('select', s.id))
      .addTo(layer!)
    if (i < 5) points.push([s.lat, s.lon])
    if (selected) marker.openTooltip()
  })

  if (points.length > 1) m.fitBounds(lib.latLngBounds(points), { padding: [36, 36], maxZoom: 16 })
  else m.setView([props.house.lat, props.house.lon], 15)
}

onMounted(async () => {
  try {
    const lib = await import('leaflet')
    L.value = lib
    if (!el.value) return
    map.value = lib
      .map(el.value, { zoomControl: true, attributionControl: true })
      .setView([props.house.lat, props.house.lon], 15)
    lib
      .tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; участники OpenStreetMap',
      })
      .addTo(map.value)
    render()
  } catch {
    failed.value = true
  }
})

watch(() => [props.shelters, props.me, props.selectedId], render, { deep: false })

onBeforeUnmount(() => {
  map.value?.remove()
  map.value = null
})

function focus(id: number): void {
  const s = props.shelters.find((x) => x.id === id)
  if (s && map.value) map.value.flyTo([s.lat, s.lon], 17, { duration: 0.6 })
}
defineExpose({ focus })
</script>

<template>
  <div class="relative isolate overflow-hidden rounded-[20px]">
    <div
      ref="el"
      class="h-[280px] w-full"
      role="application"
      aria-label="Карта укрытий рядом с домом"
    />
    <div
      v-if="failed"
      class="text-muted absolute inset-0 flex items-center justify-center bg-surface-variant p-4 text-center text-sm"
    >
      Карта не загрузилась. Список укрытий ниже.
    </div>
  </div>
</template>

<style>
.kz-pin span {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 3px solid #fff;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.35);
  color: #fff;
  font-size: 18px;
}
.leaflet-container {
  font: inherit;
}
</style>
