from pydub import AudioSegment
import os
import time
import requests
import pandas as pd
from dotenv import load_dotenv
import anthropic
import asyncio
import hashlib
import json
from datetime import timedelta
from moviepy import VideoFileClip

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
CLAUDE_API_KEY   = os.getenv('CLAUDE_API_KEY')
CLAUDE_MODEL     = os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-5')


# ============================================================
# КЭШ
# ============================================================

def get_request_hash(text, prompt):
    combined = f"{text[:1000]}_{prompt[:500]}"
    return hashlib.md5(combined.encode('utf-8')).hexdigest()


def load_cached_response(request_hash, cache_folder='Files/GPT_Cache'):
    os.makedirs(cache_folder, exist_ok=True)
    cache_file = os.path.join(cache_folder, f"{request_hash}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"📋 Кэш найден: {request_hash[:8]}...")
                return data['response']
        except Exception as e:
            print(f"⚠️  Ошибка кэша: {e}")
    return None


def save_cached_response(request_hash, response, text, prompt, cache_folder='Files/GPT_Cache'):
    os.makedirs(cache_folder, exist_ok=True)
    cache_file = os.path.join(cache_folder, f"{request_hash}.json")
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                'response': response,
                'text_preview': text[:200],
                'prompt_preview': prompt[:200],
                'timestamp': time.time()
            }, f, ensure_ascii=False, indent=2)
        print(f"💾 Кэш сохранён: {request_hash[:8]}...")
    except Exception as e:
        print(f"⚠️  Ошибка сохранения кэша: {e}")


# ============================================================
# CLAUDE ASYNC
# ============================================================

async def chat_question_claude_async(question, semaphore, temperature=0, prep=""):
    """Асинхронный запрос к Claude с семафором."""
    async with semaphore:
        client = anthropic.AsyncAnthropic(api_key=CLAUDE_API_KEY)
        for attempt in range(5):
            try:
                message = await client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=8096,
                    temperature=temperature,
                    system=prep,
                    messages=[{"role": "user", "content": question}]
                )
                return message.content[0].text
            except anthropic.RateLimitError:
                wait = 10 * (attempt + 1)
                print(f"⚠️  Rate limit, ждём {wait}с (попытка {attempt+1}/5)...")
                await asyncio.sleep(wait)
            except anthropic.APIError as e:
                print(f"❌ API ошибка: {e}")
                raise
        raise RuntimeError("Все попытки исчерпаны (rate limit)")


async def process_chunk_async(chunk_num, total, chunk_text, prompt, improved_folder,
                               final_path, all_results, semaphore, cache_folder='Files/GPT_Cache'):
    """Обрабатывает один чанк асинхронно."""
    chunk_file  = f'chunk_{chunk_num}.txt'
    improved_path = os.path.join(improved_folder, chunk_file)

    if os.path.exists(improved_path):
        with open(improved_path, 'r', encoding='utf-8') as f:
            improved_text = f.read()
        print(f"📋 Чанк {chunk_num}/{total} уже обработан, загружаем")
        all_results[chunk_num] = improved_text
        return

    request_hash = get_request_hash(chunk_text, prompt)
    cached = load_cached_response(request_hash, cache_folder)
    if cached is not None:
        all_results[chunk_num] = cached
        with open(improved_path, 'w', encoding='utf-8') as f:
            f.write(cached)
        return

    print(f"🚀 Claude: чанк {chunk_num}/{total} (хеш: {request_hash[:8]})...")
    improved_text = await chat_question_claude_async(chunk_text, semaphore, temperature=0, prep=prompt)
    improved_text = '\n'.join([line for line in improved_text.splitlines() if line.strip()])

    with open(improved_path, 'w', encoding='utf-8') as f:
        f.write(improved_text)
    save_cached_response(request_hash, improved_text, chunk_text, prompt, cache_folder)

    print(f"✅ Готов чанк {chunk_num}/{total}")
    all_results[chunk_num] = improved_text

    ready = [all_results[k] for k in sorted(all_results.keys())]
    with open(final_path, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(ready))
    print(f"📄 Final TXT обновлён ({len(ready)}/{total} готово)")


# ============================================================
# DEEPGRAM
# ============================================================

def nova_full(audio_path, language='ru', max_retries=5, retry_delay=5):
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    print(f"📤 Deepgram: {audio_path} ({file_size_mb:.1f} MB)")

    audio = AudioSegment.from_file(audio_path)
    duration_min = len(audio) / 60000
    timeout = max(300, int(duration_min * 6) + 120)
    print(f"⏱️  Длительность: {duration_min:.1f} мин, таймаут: {timeout} сек")
    del audio

    for attempt in range(max_retries):
        try:
            with open(audio_path, 'rb') as f:
                audio_data = f.read()

            url = f"https://api.deepgram.com/v1/listen?model=nova-2&language={language}&diarize=true"
            headers = {
                "Authorization": f'Token {DEEPGRAM_API_KEY}',
                "Content-Type": 'audio/mpeg'
            }
            print(f"📡 Deepgram (попытка {attempt+1}/{max_retries})...")
            response = requests.post(url, headers=headers, data=audio_data, timeout=timeout)
            response.raise_for_status()

            df = pd.json_normalize(
                response.json(),
                record_path=['results', 'channels', 'alternatives', 'words']
            )
            for col in ['start', 'end', 'confidence', 'speaker_confidence']:
                if col in df.columns:
                    df[col] = df[col].round(2)

            print(f"✅ Deepgram: {len(df)} слов, {df['speaker'].nunique()} спикеров")
            return df

        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
            if attempt < max_retries - 1:
                wait = retry_delay * (attempt + 1)
                print(f"⚠️  Попытка {attempt+1} не удалась: {e}. Повтор через {wait}с...")
                time.sleep(wait)
            else:
                print(f"❌ Все попытки исчерпаны: {e}")
                return pd.DataFrame()
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            return pd.DataFrame()


# ============================================================
# ТРАНСКРИПТ ИЗ DATAFRAME
# ============================================================

def format_time(seconds):
    td = timedelta(seconds=int(seconds))
    total_seconds = int(td.total_seconds())
    hours   = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs    = total_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def df_to_dialogue(df):
    if df.empty:
        return []

    result = []
    current_speaker = None
    current_words   = []
    start_time      = None
    end_time        = None

    for _, row in df.iterrows():
        speaker = int(row['speaker'])
        word    = str(row['word'])
        start   = row['start']
        end     = row['end']

        if speaker != current_speaker and current_speaker is not None:
            result.append(f"{format_time(start_time)} - {format_time(end_time)} Спикер{current_speaker}: {' '.join(current_words)}")
            current_words = [word]
            start_time    = start
            end_time      = end
            current_speaker = speaker
        else:
            current_words.append(word)
            if start_time is None:
                start_time = start
            end_time       = end
            current_speaker = speaker

    if current_words:
        result.append(f"{format_time(start_time)} - {format_time(end_time)} Спикер{current_speaker}: {' '.join(current_words)}")

    return result


def split_transcript_to_chunks(lines, chunk_duration_min=3):
    if not lines:
        return []

    chunk_duration_sec = chunk_duration_min * 60
    chunks             = []
    current_chunk      = []
    chunk_start_sec    = 0

    for line in lines:
        time_part = line.split(' - ')[0].strip()
        parts     = time_part.split(':')
        if len(parts) == 3:
            line_start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            line_start_sec = int(parts[0]) * 60 + int(parts[1])

        if line_start_sec >= chunk_start_sec + chunk_duration_sec and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk   = []
            chunk_start_sec = line_start_sec

        current_chunk.append(line)

    if current_chunk:
        chunks.append('\n'.join(current_chunk))

    return chunks


# ============================================================
# ВИДЕО → АУДИО
# ============================================================

def extract_audio_from_video(video_path, output_folder='Files/Extracted Audio'):
    os.makedirs(output_folder, exist_ok=True)
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    audio_path = os.path.join(output_folder, f"{video_name}.mp3")

    if os.path.exists(audio_path):
        print(f"📁 Аудио уже извлечено: {audio_path}")
        return audio_path

    print("🎵 Извлекаем аудио из видео...")
    video = VideoFileClip(video_path)
    video.audio.write_audiofile(audio_path, logger=None)
    video.close()
    print(f"✅ Аудио: {audio_path}")
    return audio_path
