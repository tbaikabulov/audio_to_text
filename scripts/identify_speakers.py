"""
Скрипт для идентификации и замены спикеров в финальном транскрипте.

Шаги:
1. Читает финальный TXT файл (из переменной FILE_PATH ниже)
2. Собирает по 5 характерных реплик для каждого спикера
3. Выводит их в терминал — ты смотришь и определяешь кто есть кто
4. Ты вводишь имена (например: Спикер0 → Ремесло, Спикер1 → Собчак)
5. Заменяет все метки в файле и сохраняет

Запуск: python scripts_v3/identify_speakers.py
"""

import os
import re
from collections import defaultdict


# ============================================================
# УКАЖИ ПУТЬ К ФАЙЛУ ЗДЕСЬ
# ============================================================
FILE_PATH = 'Files/Final TXT/где мои дети 2.txt'
# ============================================================


def extract_speaker_samples(file_path, samples_per_speaker=5, min_length=40):
    """
    Извлекает по N характерных реплик для каждого спикера.
    Берёт реплики из середины файла (не начало/конец) и достаточной длины.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f if l.strip()]

    speaker_lines = defaultdict(list)
    pattern = re.compile(r'^[\d:]+\s*-\s*[\d:]+\s+(Спикер\d+):\s+(.+)$')

    for line in lines:
        m = pattern.match(line)
        if m:
            speaker  = m.group(1)
            text     = m.group(2)
            if len(text) >= min_length:
                speaker_lines[speaker].append((line, text))

    samples = {}
    for speaker, items in sorted(speaker_lines.items()):
        total = len(items)
        if total == 0:
            continue
        # Берём из середины файла — там меньше вводных фраз
        start = max(0, total // 4)
        end   = min(total, start + samples_per_speaker * 3)
        pool  = items[start:end]
        # Выбираем самые длинные реплики из пула
        pool.sort(key=lambda x: len(x[1]), reverse=True)
        samples[speaker] = pool[:samples_per_speaker]

    return samples, speaker_lines


def replace_speakers(file_path, mapping):
    """Заменяет метки спикеров в файле согласно маппингу {Спикер0: Имя}."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Сортируем по убыванию номера чтобы Спикер10 не стал Спикер1+0
    for speaker, name in sorted(mapping.items(), key=lambda x: x[0], reverse=True):
        content = content.replace(f'{speaker}:', f'{name}:')

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\n✅ Сохранено: {file_path}")


def main():
    file_path = FILE_PATH
    print(f"📄 Файл: {file_path}\n")

    if not os.path.exists(file_path):
        print(f"❌ Файл не найден: {file_path}")
        return

    samples, speaker_lines = extract_speaker_samples(file_path)

    if not samples:
        print("❌ Спикеры не найдены в файле.")
        return

    # ── Вывод примеров ───────────────────────────────────────────────
    print("=" * 70)
    print("ПРИМЕРЫ РЕПЛИК ПО СПИКЕРАМ")
    print("=" * 70)

    for speaker, items in sorted(samples.items()):
        total = len(speaker_lines[speaker])
        print(f"\n{'─'*70}")
        print(f"  {speaker}  ({total} реплик всего)")
        print(f"{'─'*70}")
        for i, (line, _) in enumerate(items, 1):
            # Обрезаем длинные реплики для читаемости
            display = line if len(line) <= 120 else line[:117] + "..."
            print(f"  {i}. {display}")

    # ── Ввод имён ────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("ВВЕДИ ИМЕНА СПИКЕРОВ")
    print("(Enter — оставить метку как есть, например 'Спикер2')")
    print("=" * 70)

    mapping = {}
    for speaker in sorted(samples.keys()):
        name = input(f"\n  {speaker} → ").strip()
        if name:
            mapping[speaker] = name
        else:
            print(f"  ↳ Оставляем '{speaker}'")

    if not mapping:
        print("\n⚠️  Имена не введены, файл не изменён.")
        return

    # ── Предпросмотр ─────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("ЗАМЕНЫ:")
    for speaker, name in sorted(mapping.items()):
        count = len(speaker_lines[speaker])
        print(f"  {speaker} → {name}  ({count} реплик)")

    confirm = input("\nПрименить? [y/n]: ").strip().lower()
    if confirm != 'y':
        print("Отменено.")
        return

    replace_speakers(file_path, mapping)

FILE_PATH = 'Files/Final TXT/2026-05-14 19-00-30.txt'

if __name__ == '__main__':
    main()




# python scripts_v3/identify_speakers.py
