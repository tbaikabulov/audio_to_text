import sys
import os
import re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from functions import *
import asyncio


# Лимиты Claude по тирам:
#   Tier 1 (от $5):  50  RPM → MAX_CONCURRENT = 5
#   Tier 2 (от $40): 1000 RPM → MAX_CONCURRENT = 20
#   Tier 3 (от $200): 2000 RPM → MAX_CONCURRENT = 40
MAX_CONCURRENT = 5


ANALYTICS_KEYWORDS = {
    'python', 'sql', 'select', 'join', 'group by', 'having', 'where', 'cte',
    'tableau', 'power bi', 'superset', 'bigquery', 'clickhouse', 'postgres',
    'метрика', 'метрики', 'конверсия', 'воронка', 'когорта', 'ретеншн', 'retention',
    'ab тест', 'a/b', 'a b тест', 'эксперимент', 'гипотеза', 'p-value', 'статзначимость',
    'arpu', 'arppu', 'ltv', 'romi', 'roi', 'дашборд', 'корреляция', 'регрессия'
}


def infer_transcript_mode_and_domain(lines):
    """
    Определяет режим обработки:
      - dialogue: несколько активных спикеров
      - monologue: один доминирующий спикер
    И определяет, есть ли контекст data analytics.
    """
    if not lines:
        return {'mode': 'dialogue', 'is_analytics': False}

    first_probe = lines[: min(30, len(lines))]
    speaker_pattern = re.compile(r'Спикер(\d+):')
    speaker_counts = defaultdict(int)

    for line in first_probe:
        m = speaker_pattern.search(line)
        if m:
            speaker_counts[m.group(1)] += 1

    total_with_speaker = sum(speaker_counts.values())
    mode = 'dialogue'
    if total_with_speaker > 0:
        top_share = max(speaker_counts.values()) / total_with_speaker
        if len(speaker_counts) <= 1 or top_share >= 0.9:
            mode = 'monologue'

    probe_text = '\n'.join(first_probe).lower()
    is_analytics = any(keyword in probe_text for keyword in ANALYTICS_KEYWORDS)

    return {'mode': mode, 'is_analytics': is_analytics}


def build_system_prompt(lines):
    """
    Создает адаптивный system prompt:
    - если тематика аналитическая, включает контекст data analytics
    - если формат монолог, просит делать цельный текст
    - если формат диалог, сохраняет формат с таймкодами и СпикерN
    """
    detected = infer_transcript_mode_and_domain(lines)
    mode = detected['mode']
    is_analytics = detected['is_analytics']

    common_block = """
Перед тобой ASR-расшифровка на русском языке.
Исправь пунктуацию, явные ошибки распознавания и опечатки, не меняя смысл.
Не придумывай новые реплики и не добавляй факты, которых нет в тексте.
""".strip()

    analytics_block = """
Тематика похожа на data analytics.
Уделяй особое внимание корректности терминов: Python, SQL, A/B-тесты, метрики, продуктовая аналитика.
Если термин искажен, восстанови наиболее вероятный вариант по контексту (например, HAVING, ARPPU, retention).
""".strip()

    dialogue_block = """
Это диалог нескольких людей.
Сохрани построчный формат:
MM:SS - MM:SS СпикерN: текст
Метки Спикер0, Спикер1 и т.д. не переименовывай.
""".strip()

    monologue_block = """
Это, вероятно, монолог (один основной спикер).
Сделай связный читаемый текст без искусственного разделения на несколько спикеров.
Разрешено убрать префиксы СпикерN и таймкоды.
Сохраняй исходный порядок мыслей и полноту содержания.
""".strip()

    blocks = [common_block]
    if is_analytics:
        blocks.append(analytics_block)
    blocks.append(monologue_block if mode == 'monologue' else dialogue_block)
    return '\n\n'.join(blocks), detected


def extract_speaker_samples(file_path, samples_per_speaker=5, min_length=40):
    """Извлекает по N характерных реплик для каждого спикера из финального TXT."""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f if l.strip()]

    speaker_lines = defaultdict(list)
    pattern = re.compile(r'^[\d:]+\s*-\s*[\d:]+\s+(Спикер\d+):\s+(.+)$')

    for line in lines:
        m = pattern.match(line)
        if m:
            speaker = m.group(1)
            text = m.group(2)
            if len(text) >= min_length:
                speaker_lines[speaker].append((line, text))

    samples = {}
    for speaker, items in sorted(speaker_lines.items()):
        total = len(items)
        if total == 0:
            continue
        start = max(0, total // 4)
        end = min(total, start + samples_per_speaker * 3)
        pool = items[start:end]
        pool.sort(key=lambda x: len(x[1]), reverse=True)
        samples[speaker] = pool[:samples_per_speaker]

    return samples, speaker_lines


def replace_speakers(file_path, mapping):
    """Заменяет метки спикеров в файле согласно маппингу {Спикер0: Имя}."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    for speaker, name in sorted(mapping.items(), key=lambda x: x[0], reverse=True):
        content = content.replace(f'{speaker}:', f'{name}:')

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


def identify_speakers_interactive(file_path):
    """Показывает примеры реплик, запрашивает имена и заменяет метки в файле."""
    print(f"\n{'=' * 70}")
    print("ИДЕНТИФИКАЦИЯ СПИКЕРОВ")
    print(f"{'=' * 70}")

    samples, speaker_lines = extract_speaker_samples(file_path)
    if not samples:
        print("⚠️  Спикеры (Спикер0, Спикер1, …) не найдены — пропускаем.")
        return

    print("\nПРИМЕРЫ РЕПЛИК ПО СПИКЕРАМ")
    for speaker, items in sorted(samples.items()):
        total = len(speaker_lines[speaker])
        print(f"\n{'─' * 70}")
        print(f"  {speaker}  ({total} реплик всего)")
        print(f"{'─' * 70}")
        for i, (line, _) in enumerate(items, 1):
            display = line if len(line) <= 120 else line[:117] + "..."
            print(f"  {i}. {display}")

    print(f"\n{'=' * 70}")
    print("ВВЕДИ ИМЕНА СПИКЕРОВ")
    print("(Enter — оставить метку как есть)")
    print("=" * 70)

    mapping = {}
    for speaker in sorted(samples.keys()):
        name = input(f"\n  {speaker} → ").strip()
        if name:
            mapping[speaker] = name

    if not mapping:
        print("\n⚠️  Имена не введены, файл не изменён.")
        return

    print(f"\n{'─' * 70}")
    print("ЗАМЕНЫ:")
    for speaker, name in sorted(mapping.items()):
        print(f"  {speaker} → {name}  ({len(speaker_lines[speaker])} реплик)")

    confirm = input("\nПрименить? [y/n]: ").strip().lower()
    if confirm != 'y':
        print("Отменено.")
        return

    replace_speakers(file_path, mapping)
    print(f"✅ Спикеры заменены: {file_path}")


async def process_audio_v3(file_path, prompt, chunk_duration_min=3, remove_old=True, identify_speakers=True):
    """
    Пайплайн v3: то же что v2, но чанки отправляются в Claude параллельно.
    Deepgram → текст → нарезка → параллельный Claude → финальный файл.
    """
    file_name = os.path.splitext(os.path.basename(file_path))[0]

    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    ext = os.path.splitext(file_path)[1].lower()
    audio_path = extract_audio_from_video(file_path) if ext in video_extensions else file_path

    nova_csv_path   = f'Files/NOVA files/{file_name}_full.csv'
    transcript_path = f'Files/Transcripts/{file_name}_full.txt'
    improved_folder = f'Files/Transcripts_Improved/{file_name}'
    final_path      = f'Files/Final TXT/{file_name}.txt'

    if remove_old:
        for path in [nova_csv_path, transcript_path, final_path]:
            if os.path.isfile(path):
                os.remove(path)
        if os.path.isdir(improved_folder):
            for f in os.listdir(improved_folder):
                os.remove(os.path.join(improved_folder, f))
            os.rmdir(improved_folder)

    os.makedirs('Files/NOVA files',   exist_ok=True)
    os.makedirs('Files/Transcripts',  exist_ok=True)
    os.makedirs(improved_folder,      exist_ok=True)
    os.makedirs('Files/Final TXT',    exist_ok=True)

    # ====== ШАГ 1: Deepgram ======
    if os.path.exists(nova_csv_path):
        print(f"📋 NOVA CSV уже существует: {nova_csv_path}")
        df = pd.read_csv(nova_csv_path)
    else:
        df = nova_full(audio_path)
        if df.empty:
            print("❌ Deepgram вернул пустой результат.")
            return
        df.to_csv(nova_csv_path, index=False)
        print(f"💾 NOVA CSV сохранён: {nova_csv_path} ({len(df)} слов)")

    # ====== ШАГ 2: Транскрипт ======
    if os.path.exists(transcript_path):
        print(f"📋 Транскрипт уже существует: {transcript_path}")
        with open(transcript_path, 'r', encoding='utf-8') as f:
            lines = f.read().strip().split('\n')
    else:
        lines = df_to_dialogue(df)
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f"📝 Транскрипт: {transcript_path} ({len(lines)} реплик)")

    speakers = df['speaker'].unique()
    print(f"🎤 Спикеров: {len(speakers)} ({sorted(speakers.tolist())})")

    # ====== ШАГ 3: Нарезка на чанки ======
    chunks = split_transcript_to_chunks(lines, chunk_duration_min=chunk_duration_min)
    print(f"✂️  Чанков: {len(chunks)} (~{chunk_duration_min} мин каждый)")
    print(f"⚡ Параллельность: {MAX_CONCURRENT} одновременных запросов")

    adaptive_prompt, detected = build_system_prompt(lines)
    prompt_to_use = adaptive_prompt if prompt in (None, '', 'auto') else prompt
    print(
        "🧠 Режим:"
        f" {'монолог' if detected['mode'] == 'monologue' else 'диалог'},"
        f" analytics={'да' if detected['is_analytics'] else 'нет'}"
    )

    # ====== ШАГ 4: Параллельный Claude ======
    semaphore   = asyncio.Semaphore(MAX_CONCURRENT)
    all_results = {}

    tasks = [
        process_chunk_async(
            chunk_num=i + 1,
            total=len(chunks),
            chunk_text=chunk_text,
            prompt=prompt_to_use,
            improved_folder=improved_folder,
            final_path=final_path,
            all_results=all_results,
            semaphore=semaphore
        )
        for i, chunk_text in enumerate(chunks)
    ]

    await asyncio.gather(*tasks)

    ordered = [all_results[k] for k in sorted(all_results.keys())]
    with open(final_path, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(ordered))

    print(f"\n✅ Готово! Финальный файл: {final_path}")

    if identify_speakers and detected['mode'] != 'monologue':
        identify_speakers_interactive(final_path)


# ============================================================
# ЗАПУСК
# ============================================================

file_path = '/Volumes/K4/Корзина для больших файлов/2025-07-01 Лия созвон про тг контент.mov'


asyncio.run(process_audio_v3(file_path, prompt='auto', chunk_duration_min=3, remove_old=False))

# python scripts_v3/process_audio.py
