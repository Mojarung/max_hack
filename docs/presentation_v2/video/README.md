# Ролик «Домовой Кузя»

30 секунд, 2560×1440, 60 кадров в секунду. Сцены, таймлайн и звуковые метки описаны в `index.html`, сборка в `render.py`.

- iPhone - 3D-модель на Three.js в настоящих размерах (71,6 × 147,6 × 7,8 мм): титановая рамка, стекло с отражениями окружения, Dynamic Island, блок из трёх камер и вспышка сзади, кнопки. Экран живой: сообщения чата приходят прямо на нём, видны нажатия пальцем и вспышка камеры.
- Пока на экране текст, телефон стоит почти анфас и только чуть покачивается, чтобы экран читался. Развороты через спину, переворот через верх, наезд камеры на карту и карусель из пяти телефонов только в переходах.
- Кузя собран из слоёв позы и живёт каждый кадр: пружинит в долю музыки, качает головой, моргает.

Пересобрать ролик (нужны Chrome и ffmpeg; страница открывается через локальный HTTP-сервер, иначе WebGL не примет скриншоты):

```bash
uv run --with playwright python docs/presentation_v2/video/render.py
uv run --with playwright python docs/presentation_v2/video/render.py --preview 3 9.6 21.7   # отдельные кадры в build/
```

Готовый `Ролик_Домовой_Кузя.mp4` (около 30 МБ) не хранится в git: скрипт кладёт его в корень репозитория, файл игнорируется.

## Звуки

Все звуки с Freesound под лицензией CC0, найдены через Openverse. Указывать авторство не обязательно, но указываем.

| Файл | Название | Автор | Страница |
|---|---|---|---|
| `music_positive_weekend.mp3` | Positive Weekend | Antenalosmusic | https://freesound.org/people/Antenalosmusic/sounds/713065 |
| `bubble.mp3` | Bubble | deleted_user_3854053 | https://freesound.org/people/deleted_user_3854053/sounds/269583 |
| `riser.mp3` | Riser | Rizzard | https://freesound.org/people/Rizzard/sounds/561207 |
| `whoosh1.mp3` | Swipe Whoosh | qubodup | https://freesound.org/people/qubodup/sounds/60007 |
| `whoosh2.mp3` | Swosh swoosh whoosh air sound, free, high quality | qubodup | https://freesound.org/people/qubodup/sounds/60026 |
| `whoosh_deep.mp3` | Deep Whoosh #1 | Kinoton | https://freesound.org/people/Kinoton/sounds/351256 |
| `poppy.mp3` | cartoon poppyup appearances -0005.aiff | martian | https://freesound.org/people/martian/sounds/19288 |
| `chime.mp3` | Chime Notification | Jofae | https://freesound.org/people/Jofae/sounds/380482 |
| `shutter.mp3` | Camera Shutter | roachpowder | https://freesound.org/people/roachpowder/sounds/170229 |
| `click.mp3` | UI Button Click | benzix2 | https://freesound.org/people/benzix2/sounds/467951 |
| `success.mp3` | SFX-Success!.wav | HenryRichard | https://freesound.org/people/HenryRichard/sounds/448274 |
| `ding.mp3` | Ding 1 | greenvwbeetle | https://freesound.org/people/greenvwbeetle/sounds/241288 |
| `message.mp3` | Message sound.wav | Sunart1 | https://freesound.org/people/Sunart1/sounds/592772 |
