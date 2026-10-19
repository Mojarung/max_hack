import { onBeforeUnmount, onMounted } from 'vue'

/**
 * Свайп пальцем влево-вправо по экрану переключает соседнюю вкладку, как в iOS.
 * Слушаем touch-события: pointer-события браузер отменяет, как только начинает прокрутку.
 * Жест в лентах чипов, каруселях и полях ввода не трогаем, там палец листает своё.
 */
// Сдвиг пальца, после которого жест считается свайпом
const SWIPE_MIN_PX = 60
// Свайп должен быть заметно горизонтальным, иначе это прокрутка страницы
const HORIZONTAL_RATIO = 1.6
const IGNORE =
  '.chips-scroll, .photo-carousel, input, textarea, [data-no-swipe], .leaflet-container, .segmented'

export function useSwipeTabs(
  area: () => HTMLElement | null | undefined,
  onSwipe: (step: 1 | -1) => void,
): void {
  let startX = 0
  let startY = 0
  let tracking = false

  const start = (e: TouchEvent) => {
    const touch = e.touches[0]
    tracking = e.touches.length === 1 && !!touch && !(e.target as Element | null)?.closest(IGNORE)
    if (!touch) return
    startX = touch.clientX
    startY = touch.clientY
  }
  const end = (e: TouchEvent) => {
    const touch = e.changedTouches[0]
    if (!tracking || !touch) return
    tracking = false
    const dx = touch.clientX - startX
    const dy = touch.clientY - startY
    if (Math.abs(dx) < SWIPE_MIN_PX || Math.abs(dx) < Math.abs(dy) * HORIZONTAL_RATIO) return
    // палец ушёл влево - открываем следующую вкладку
    onSwipe(dx < 0 ? 1 : -1)
  }
  const cancel = () => (tracking = false)

  let el: HTMLElement | null = null
  onMounted(() => {
    el = area() ?? null
    el?.addEventListener('touchstart', start, { passive: true })
    el?.addEventListener('touchend', end, { passive: true })
    el?.addEventListener('touchcancel', cancel, { passive: true })
  })
  onBeforeUnmount(() => {
    el?.removeEventListener('touchstart', start)
    el?.removeEventListener('touchend', end)
    el?.removeEventListener('touchcancel', cancel)
  })
}
