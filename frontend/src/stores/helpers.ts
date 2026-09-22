/** Сбросчики сторов: вызываются при смене демо-жителя. */
const resetters = new Set<() => void>()

export function registerReset(fn: () => void): void {
  resetters.add(fn)
}

export function resetAllStores(): void {
  resetters.forEach((fn) => fn())
}

/**
 * Вставляет или заменяет элемент по id, не мутируя массив.
 * `keep` - поля, которые берём из локальной версии (например, `voted_by_me`:
 * в широковещательном SSE-событии они посчитаны не для текущего жителя).
 */
export function upsertById<T extends { id: number | string }>(
  list: readonly T[],
  item: T,
  options: { keep?: (keyof T)[]; prepend?: boolean; onlyExisting?: boolean } = {},
): T[] {
  const index = list.findIndex((x) => x.id === item.id)
  if (index === -1) {
    if (options.onlyExisting) return [...list]
    return options.prepend ? [item, ...list] : [...list, item]
  }
  const current = list[index]!
  const merged = { ...current, ...item }
  for (const key of options.keep ?? []) merged[key] = current[key]
  return [...list.slice(0, index), merged, ...list.slice(index + 1)]
}

export function removeById<T extends { id: number | string }>(
  list: readonly T[],
  id: T['id'],
): T[] {
  return list.filter((x) => x.id !== id)
}
