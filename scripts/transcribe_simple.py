"""
Простая транскрипция без разбивки по спикерам.
Deepgram (любой язык) → сырой текст → Claude → дословный текст на русском.

Запуск: python scripts_v3/transcribe_simple.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from functions import *

import anthropic
import requests


def nova_simple(audio_path, language='en', max_retries=5, retry_delay=5):
    """Deepgram без диаризации — возвращает сырую строку транскрипта."""
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    print(f"📤 Deepgram: {audio_path} ({file_size_mb:.1f} MB)")

    audio = AudioSegment.from_file(audio_path)
    duration_min = len(audio) / 60000
    timeout = max(300, int(duration_min * 60 * 2))
    print(f"⏱️  Длительность: {duration_min:.1f} мин, язык: {language}")

    import io
    buf = io.BytesIO()
    audio.export(buf, format='mp3')
    audio_data = buf.getvalue()

    url = f"https://api.deepgram.com/v1/listen?model=nova-2&language={language}&punctuate=true&paragraphs=true"
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "audio/mpeg",
    }

    for attempt in range(max_retries):
        try:
            print(f"📡 Deepgram (попытка {attempt+1}/{max_retries})...")
            response = requests.post(url, headers=headers, data=audio_data, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            transcript = (
                data.get("results", {})
                    .get("channels", [{}])[0]
                    .get("alternatives", [{}])[0]
                    .get("transcript", "")
            )
            words = len(transcript.split())
            print(f"✅ Deepgram: {words} слов распознано")
            return transcript
        except Exception as e:
            print(f"⚠️  Ошибка: {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
    return ""


def claude_verbatim(transcript, source_language='en'):
    """Отправляет сырой транскрипт в Claude, получает дословный текст на русском."""
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    prompt = f"""Тебе дана автоматическая расшифровка аудио/видео на языке '{source_language}'.

Задача: передай дословно всё, что было сказано, на русском языке.
- Переводи максимально близко к оригиналу, сохраняя стиль и интонацию
- Не сокращай, не резюмируй — передай каждое предложение
- Убери только явные артефакты распознавания (повторы одного слова подряд)
- Без временных меток, без разбивки по спикерам — просто текст

РАСШИФРОВКА:
{transcript}"""

    print("🤖 Claude: перевод на русский...")
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def transcribe_simple(file_path, language='en'):
    """
    Пайплайн: Deepgram (без диаризации) → Claude (дословный перевод на русский).
    """
    file_name = os.path.splitext(os.path.basename(file_path))[0]

    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    ext = os.path.splitext(file_path)[1].lower()
    audio_path = extract_audio_from_video(file_path) if ext in video_extensions else file_path

    out_dir = 'Files/Simple TXT'
    os.makedirs(out_dir, exist_ok=True)
    out_path = f'{out_dir}/{file_name}.txt'

    # Шаг 1: Deepgram
    transcript = nova_simple(audio_path, language=language)
    if not transcript.strip():
        print("❌ Deepgram вернул пустой транскрипт.")
        return

    # Шаг 2: Claude
    result = claude_verbatim(transcript, source_language=language)

    # Сохранение
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(result)

    print(f"\n✅ Готово! Файл: {out_path}")
    print("─" * 60)
    print(result[:500] + ("..." if len(result) > 500 else ""))


# ============================================================
# ЗАПУСК
# ============================================================

file_path = '/Users/tfbaykabulov/Documents/CURSOR projects/audio_to_text/Files/Extracted Audio/Breaking News_ Some Bullshit Happening Somewhere.mp3'
language  = 'en'   # язык оригинала: 'en', 'ru', 'de', и т.д.

transcribe_simple(file_path, language=language)

# python scripts_v3/transcribe_simple.py
