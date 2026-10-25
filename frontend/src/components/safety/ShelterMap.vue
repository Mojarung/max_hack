<script setup lang="ts">
import 'leaflet/dist/leaflet.css'
import type * as Leaflet from 'leaflet'
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import type { RouteOut, ShelterOut } from '@/api/types'
import { formatDistance } from '@/utils/format'

const props = defineProps<{
  house: { lat: number; lon: number; title: string }
  shelters: ShelterOut[]
  me?: { lat: number; lon: number; source: 'gps' | 'house' } | null
  selectedId?: number | null
  /** Маршрут до выбранного укрытия: сплошная линия от OSRM, пунктир - прямая по воздуху. */
  route?: RouteOut | null
}>()
const emit = defineEmits<{ select: [id: number] }>()

const el = ref<HTMLElement | null>(null)
const failed = ref(false)
const L = shallowRef<typeof Leaflet | null>(null)
const map = shallowRef<Leaflet.Map | null>(null)
let layer: Leaflet.LayerGroup | null = null
let routeLayer: Leaflet.Polyline | null = null

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
}

/** Цвет из токена темы Vuetify (`--v-theme-primary` хранит «r,g,b»), чтобы линия жила в обеих темах. */
function themeColor(token: string): string {
  const rgb = getComputedStyle(document.documentElement).getPropertyValue(`--v-theme-${token}`)
  return `rgb(${rgb.trim() || '0,0,0'})`
}

/** Кружок `size` px, но зона нажатия не меньше 44px (DESIGN.md). */
function pin(lib: typeof Leaflet, icon: string, bg: string, size = 34): Leaflet.DivIcon {
  const hit = Math.max(44, size)
  return lib.divIcon({
    className: 'kz-pin',
    html: `<span style="background:${bg};width:${size}px;height:${size}px"><i class="mdi ${icon}"></i></span>`,
    iconSize: [hit, hit],
    iconAnchor: [hit / 2, hit / 2],
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
      icon: pin(lib, 'mdi-home-heart', '#03045E'),
      title: props.house.title,
    })
    .bindTooltip(escapeHtml(props.house.title))
    .addTo(layer)
  points.push([props.house.lat, props.house.lon])

  if (props.me && props.me.source === 'gps') {
    lib
      .circleMarker([props.me.lat, props.me.lon], {
        radius: 9,
        color: '#CAF0F8',
        weight: 3,
        fillColor: '#00B4D8',
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
        icon: pin(lib, 'mdi-shield-home', selected ? '#023E8A' : '#0096C7', selected ? 42 : 34),
        title: s.name,
        zIndexOffset: selected ? 1000 : 0,
      })
      // подпись над точкой: сбоку у края карты она обрезалась
      .bindTooltip(
        `${escapeHtml(s.name)}${s.distance_m !== null ? ` · ${formatDistance(s.distance_m)}` : ''}`,
        { direction: 'top', offset: [0, -20] },
      )
      .on('click', () => emit('select', s.id))
      .addTo(layer!)
    if (i < 5) points.push([s.lat, s.lon])
    if (selected) marker.openTooltip()
  })

  // Пока маршрут выбран, карта держит его в кадре, а не весь список укрытий
  if (routeLayer) m.fitBounds(routeLayer.getBounds(), { padding: [36, 36], maxZoom: 17 })
  else if (points.length > 1)
    m.fitBounds(lib.latLngBounds(points), { padding: [36, 36], maxZoom: 16 })
  else m.setView([props.house.lat, props.house.lon], 15)
}

function renderRoute(): void {
  const lib = L.value
  const m = map.value
  if (!lib || !m) return
  routeLayer?.remove()
  routeLayer = null
  if (!props.route || props.route.points.length < 2) return
  routeLayer = lib
    .polyline(props.route.points, {
      color: themeColor('primary'),
      weight: 5,
      opacity: 0.9,
      lineCap: 'round',
      lineJoin: 'round',
      dashArray: props.route.provider === 'straight' ? '8 12' : undefined,
      interactive: false,
    })
    .addTo(m)
  m.fitBounds(routeLayer.getBounds(), { padding: [36, 36], maxZoom: 17 })
}

onMounted(async () => {
  try {
    const lib = await import('leaflet')
    L.value = lib
    if (!el.value) return
    map.value = lib
      .map(el.value, { zoomControl: true, attributionControl: true })
      .setView([props.house.lat, props.house.lon], 15)
    // Без стандартного префикса Leaflet (флаг и ссылка-мелочь): оставляем только атрибуцию OSM
    map.value.attributionControl.setPrefix(false)
    lib
      .tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; участники OpenStreetMap',
      })
      .addTo(map.value)
    render()
    renderRoute()
  } catch {
    failed.value = true
  }
})

watch(() => [props.shelters, props.me, props.selectedId], render, { deep: false })
watch(() => props.route, renderRoute)

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
.kz-pin {
  display: flex;
  align-items: center;
  justify-content: center;
}
.kz-pin span {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 3px solid #caf0f8;
  box-shadow: 0 3px 10px rgba(16, 24, 40, 0.35);
  color: #caf0f8;
  font-size: 18px;
}
.leaflet-container {
  font: inherit;
}
/* Кнопки масштаба и ссылка атрибуции: крупные тач-зоны и различимая ссылка */
.leaflet-touch .leaflet-bar a {
  width: 44px;
  height: 44px;
  line-height: 44px;
}
.leaflet-control-attribution a {
  text-decoration: underline;
}
</style>
