# Фронтенд: мини-приложение MAX (Vue 3 + Vuetify 4 + Tailwind 4)

Перед любой правкой интерфейса прочитай [DESIGN.md](DESIGN.md): там принципы, палитра, компоненты и
**обязательный цикл проверки**. Правка UI не считается готовой, пока ты не посмотрел на неё сам.

## Как посмотреть приложение

- `preview_start` с `frontend-mock` (конфиг в `.claude/launch.json`) или `npm run dev:mock` → http://localhost:5174
- Мок-бэкенд в памяти (`src/mock`), без Docker и без записи в настоящий домовой чат.
  Не открывай живой бэкенд (`npm run dev`, порт 5173) для экспериментов: там реальный бот.
- Сценарии: `?scenario=default|empty|overdue|alert|long|error|boot-error`, `?role=admin`, `?theme=dark`, `?latency=2000`.
- В консоли страницы: `await __ui.audit()` (тач-зоны, мелкий текст, переполнение, axe WCAG AA).

## Проверка

- `/design-loop` - полный цикл: скриншоты, аудит, субагенты `ui-critic` и `ui-walkthrough`, исправления.
- `npm run typecheck && npm run lint && npm test` перед тем, как закончить.

## Договорённости

- Цвета только из токенов темы, никаких hex в компонентах. Палитра: синий - главное действие, смысловые цвета только для состояний, красный - только тревога и просрочка (DESIGN.md).
- Новые примитивы из Vuetify; shadcn-vue только `Drawer`, `Skeleton`, `Sonner`.
- Анимации через `composables/useMotion` и с учётом `prefersReducedMotion()`. В мок-режиме они выключены, включить: `?motion=1`.
- Кузя нарисован растром: лист поз `art/kuzya-sheet.png` режет `uv run scripts/kuzya_sprites.py` на слои тело/голова/веки в `src/components/kuzya/sprites/` и картинки в `public/`. Слои и `sprites.ts` руками не правим, только перегенерируем.
- Новые эндпоинты API - сразу добавь обработчик в `src/mock/server.ts`, иначе мок покажет пустоту.
