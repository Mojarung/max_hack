import { describe, expect, it, vi, beforeEach } from 'vitest'
import { reactive } from 'vue'
import type { RouteOut, ShelterOut } from '@/api/types'
import { HOUSE, SHELTERS } from '@/mock/fixtures'
import { getByText, queryByText, settle, waitFor } from '@/test/dom'
import { renderComponent } from '@/test/harness'
import ShelterMap from './ShelterMap.vue'

/**
 * Leaflet в jsdom не рисует карту, поэтому подменяем его записной книжкой:
 * каждый маркер, линия и сдвиг карты попадают в `calls`, а клики по маркерам можно вызвать руками.
 */
const leaflet = vi.hoisted(() => {
  type Handler = () => void
  type Fn = ReturnType<typeof vi.fn>
  interface FakeMap {
    setView: Fn
    fitBounds: Fn
    flyTo: Fn
    remove: Fn
    attributionControl: { setPrefix: Fn }
  }
  interface FakeLayer {
    kind: string
    args: unknown[]
    tooltip: string | null
    handlers: Record<string, Handler>
    opened: boolean
    removed: boolean
  }
  const state = {
    layers: [] as FakeLayer[],
    map: null as null | FakeMap,
    failMap: false,
  }
  function layer(kind: string, args: unknown[]) {
    const entry: FakeLayer = {
      kind,
      args,
      tooltip: null,
      handlers: {},
      opened: false,
      removed: false,
    }
    state.layers.push(entry)
    const api = {
      entry,
      bindTooltip(text: string) {
        entry.tooltip = text
        return api
      },
      on(event: string, handler: Handler) {
        entry.handlers[event] = handler
        return api
      },
      addTo() {
        return api
      },
      openTooltip() {
        entry.opened = true
        return api
      },
      remove() {
        entry.removed = true
        return api
      },
      getBounds: () => ({ kind: 'route-bounds' }),
    }
    return api
  }
  const module = {
    map: vi.fn(() => {
      if (state.failMap) throw new Error('нет карты')
      const m = {
        setView: vi.fn(() => m),
        fitBounds: vi.fn(() => m),
        flyTo: vi.fn(() => m),
        remove: vi.fn(),
        attributionControl: { setPrefix: vi.fn() },
      }
      state.map = m as unknown as FakeMap
      return m
    }),
    tileLayer: vi.fn((...args: unknown[]) => layer('tile', args)),
    layerGroup: vi.fn((...args: unknown[]) => layer('group', args)),
    marker: vi.fn((...args: unknown[]) => layer('marker', args)),
    circleMarker: vi.fn((...args: unknown[]) => layer('circle', args)),
    polyline: vi.fn((...args: unknown[]) => layer('polyline', args)),
    divIcon: vi.fn((options: unknown) => ({ icon: options })),
    latLngBounds: vi.fn((points: unknown) => ({ kind: 'bounds', points })),
  }
  return { state, module }
})

vi.mock('leaflet', () => ({ ...leaflet.module, default: leaflet.module }))

const house = { lat: HOUSE.lat, lon: HOUSE.lon, title: HOUSE.title }

function markers(): {
  title: unknown
  tooltip: string | null
  entry: (typeof leaflet.state.layers)[number]
}[] {
  return leaflet.state.layers
    .filter((l) => l.kind === 'marker' && !l.removed)
    .map((entry) => ({
      title: (entry.args[1] as { title?: string }).title,
      tooltip: entry.tooltip,
      entry,
    }))
}

function lastMarkers() {
  // после каждой перерисовки прежние маркеры уходят вместе со слоем, считаем только последнюю пачку
  const all = leaflet.state.layers.filter((l) => l.kind === 'marker')
  const houseIndex = all
    .map((l) => (l.args[1] as { title?: string }).title)
    .lastIndexOf(HOUSE.title)
  return all.slice(houseIndex)
}

async function renderMap(props: Record<string, unknown>) {
  const state = reactive({
    house,
    shelters: SHELTERS,
    me: null,
    selectedId: null,
    route: null,
    ...props,
  })
  const rendered = await renderComponent(ShelterMap, { props: state })
  await waitFor(() => leaflet.state.map)
  await settle()
  return { ...rendered, state, map: rendered.wrapper.findComponent(ShelterMap) }
}

beforeEach(() => {
  leaflet.state.layers = []
  leaflet.state.map = null
  leaflet.state.failMap = false
})

describe('Карта укрытий', () => {
  it('ставит дом и все укрытия с расстоянием в подписи и показывает их в одном кадре', async () => {
    await renderMap({})
    const list = lastMarkers()
    expect(list.map((m) => (m.args[1] as { title: string }).title)).toEqual([
      HOUSE.title,
      ...SHELTERS.map((s) => s.name),
    ])
    expect(list[1]!.tooltip).toBe('Укрытие в подвале школы (демо) · 180 м')
    expect(leaflet.state.map!.fitBounds).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'bounds' }),
      { padding: [36, 36], maxZoom: 16 },
    )
    expect(document.querySelector('[aria-label="Карта укрытий рядом с домом"]')).not.toBeNull()
    expect(leaflet.state.map!.attributionControl.setPrefix).toHaveBeenCalledWith(false)
  })

  it('экранирует название дома в подсказке, чтобы оно не стало разметкой', async () => {
    await renderMap({ house: { ...house, title: '<b>Дом</b>' }, shelters: [] })
    const houseMarker = leaflet.state.layers.find((l) => l.kind === 'marker')!
    expect(houseMarker.tooltip).toBe('&#60;b&#62;Дом&#60;/b&#62;')
  })

  it('без укрытий просто центрирует карту на доме', async () => {
    await renderMap({ shelters: [] })
    expect(leaflet.state.map!.fitBounds).not.toHaveBeenCalled()
    expect(leaflet.state.map!.setView).toHaveBeenLastCalledWith([HOUSE.lat, HOUSE.lon], 15)
  })

  it('показывает точку «Вы здесь» только для настоящей геопозиции', async () => {
    const { state } = await renderMap({ me: { lat: 54.38, lon: 48.6, source: 'house' } })
    expect(leaflet.state.layers.some((l) => l.kind === 'circle')).toBe(false)
    state.me = { lat: 54.38, lon: 48.6, source: 'gps' } as never
    await settle()
    const circle = leaflet.state.layers.find((l) => l.kind === 'circle')
    expect(circle?.tooltip).toBe('Вы здесь')
  })

  it('нажатие на укрытие на карте сообщает его номер', async () => {
    const { map } = await renderMap({})
    const target = markers().find((m) => m.title === SHELTERS[1]!.name)!
    target.entry.handlers.click!()
    expect(map.emitted('select')).toEqual([[SHELTERS[1]!.id]])
  })

  it('выбранное укрытие крупнее, поверх остальных и с открытой подписью', async () => {
    await renderMap({ selectedId: 2 })
    const selected = lastMarkers().find(
      (m) => (m.args[1] as { title: string }).title === SHELTERS[1]!.name,
    )!
    const options = selected.args[1] as { zIndexOffset: number; icon: { icon: { html: string } } }
    expect(options.zIndexOffset).toBe(1000)
    expect(options.icon.icon.html).toContain('width:42px')
    expect(selected.opened).toBe(true)
  })

  it('рисует маршрут: пунктир для прямой по воздуху и сплошную линию от OSRM', async () => {
    const straight: RouteOut = {
      distance_m: 300,
      duration_s: 240,
      points: [
        [54.3857, 48.6072],
        [54.3868, 48.609],
      ],
      provider: 'straight',
    }
    const { state } = await renderMap({ route: straight })
    let line = leaflet.state.layers.filter((l) => l.kind === 'polyline').at(-1)!
    expect((line.args[1] as { dashArray?: string }).dashArray).toBe('8 12')
    expect(leaflet.state.map!.fitBounds).toHaveBeenCalledWith(
      { kind: 'route-bounds' },
      { padding: [36, 36], maxZoom: 17 },
    )

    state.route = { ...straight, provider: 'osrm' } as never
    await settle()
    expect(line.removed).toBe(true)
    line = leaflet.state.layers.filter((l) => l.kind === 'polyline').at(-1)!
    expect((line.args[1] as { dashArray?: string }).dashArray).toBeUndefined()

    state.route = null
    await settle()
    expect(line.removed).toBe(true)
  })

  it('пока выбран маршрут, перерисовка держит в кадре его, а не весь список', async () => {
    const route: RouteOut = {
      distance_m: 300,
      duration_s: 240,
      points: [
        [54.3857, 48.6072],
        [54.3868, 48.609],
      ],
      provider: 'osrm',
    }
    const { state } = await renderMap({ route })
    leaflet.state.map!.fitBounds.mockClear()
    state.selectedId = 1 as never
    await settle()
    expect(leaflet.state.map!.fitBounds).toHaveBeenCalledWith(
      { kind: 'route-bounds' },
      { padding: [36, 36], maxZoom: 17 },
    )
  })

  it('маршрут из одной точки не рисуется', async () => {
    await renderMap({ route: { distance_m: 0, duration_s: 0, points: [[1, 2]], provider: 'osrm' } })
    expect(leaflet.state.layers.some((l) => l.kind === 'polyline')).toBe(false)
  })

  it('по команде снаружи плавно приближает выбранное укрытие', async () => {
    const { map } = await renderMap({})
    ;(map.vm as unknown as { focus: (id: number) => void }).focus(3)
    expect(leaflet.state.map!.flyTo).toHaveBeenCalledWith(
      [SHELTERS[2]!.lat, SHELTERS[2]!.lon],
      17,
      {
        duration: 0.6,
      },
    )
    ;(map.vm as unknown as { focus: (id: number) => void }).focus(999)
    expect(leaflet.state.map!.flyTo).toHaveBeenCalledTimes(1)
  })

  it('если карта не загрузилась, честно говорит об этом и отсылает к списку', async () => {
    leaflet.state.failMap = true
    await renderComponent(ShelterMap, { props: { house, shelters: SHELTERS as ShelterOut[] } })
    await waitFor(() => getByText('Карта не загрузилась. Список укрытий ниже.'))
  })

  it('при уходе с экрана убирает карту', async () => {
    const { wrapper } = await renderMap({})
    const m = leaflet.state.map!
    wrapper.unmount()
    expect(m.remove).toHaveBeenCalled()
    expect(queryByText('Карта не загрузилась')).toBeNull()
  })
})
