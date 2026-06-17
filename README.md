# audio_to_text

Скрипты для расшифровки аудио/видео в текст:
- Deepgram для первичной транскрипции и diarization (спикеры),
- Claude для улучшения текста и исправления ASR-ошибок,
- авто-режим `dialogue/monologue` и авто-контекст под data analytics.

## Быстрый старт

### 1) Клонировать репозиторий

```bash
git clone https://github.com/tbaikabulov/audio_to_text.git
cd audio_to_text
```

### 2) Установить Python и зависимости

Рекомендуется Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Установить FFmpeg

Нужен для `pydub`/`moviepy` (обработка аудио и извлечение из видео).

macOS:
```bash
brew install ffmpeg
```

Ubuntu/Debian:
```bash
sudo apt update
sudo apt install -y ffmpeg
```

### 4) Настроить `.env`

Скопировать шаблон:

```bash
cp .env.example .env
```

Заполнить в `.env`:
- `DEEPGRAM_API_KEY`
- `CLAUDE_API_KEY`
- `CLAUDE_MODEL` (опционально, по умолчанию берется из кода)

## Основной запуск (v3)

Файл: `scripts/process_audio.py`

1. Открой `scripts/process_audio.py`
2. Обнови `file_path` внизу файла на путь к своему `.mp3/.wav/.m4a/.mov/.mp4`
3. Запусти:

```bash
python scripts/process_audio.py
```

Результат:
- промежуточные данные: `Files/NOVA files`, `Files/Transcripts`, `Files/Transcripts_Improved`
- финальный текст: `Files/Final TXT/<имя_файла>.txt`

## Что умеет `process_audio.py`

- Авто-определяет формат по первому фрагменту:
  - `dialogue` (несколько спикеров),
  - `monologue` (один спикер доминирует).
- Авто-определяет аналитику данных по ключевым словам (`Python`, `SQL`, `A/B`, `retention`, `ARPU` и т.д.) и добавляет соответствующий контекст в prompt.
- В режиме диалога сохраняет формат:
  - `MM:SS - MM:SS СпикерN: текст`
- В режиме монолога формирует связный текст без искусственного деления по спикерам.

## Альтернативный запуск

Файл: `run.py` (старый pipeline, если нужен).

```bash
python run.py
```

## Частые проблемы

- **`ffmpeg not found`**: установить FFmpeg (см. шаг 3).
- **`Rate limit` от Claude**: подождать и запустить снова, в проекте есть кэш ответов в `Files/GPT_Cache`.
- **Пустой ответ Deepgram**: проверить API ключ и формат входного файла.

## Минимум для передачи другу

Чтобы друг скачал и сразу использовал, достаточно:
- репозиторий,
- заполненный им `.env`,
- команда `python scripts/process_audio.py`.

