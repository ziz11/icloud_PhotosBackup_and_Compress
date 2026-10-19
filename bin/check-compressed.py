#!/usr/bin/env python3
"""
Проверка полноты compressed относительно originals. Библиотека Photos не нужна,
сравниваются только каталоги на диске.

Правила отбора те же, что в step2-compress.py:
  - видео рядом с одноимённым фото (половинка Live Photo) не сжимается;
  - исходник пропускается, если есть его _edited-версия.

Для каждого отобранного оригинала ожидается один из двух файлов:
  <stem>.heic / <stem>.mp4   — сжатый результат;
  <stem>.<исходное расширение> — если сжатие не дало выигрыша и был
                                 скопирован оригинал.

Использование:
  check-compressed.py            все месяцы
  check-compressed.py 2026-08    один месяц
"""
import glob
import os
import sys

from photolib import DST, SRC, expected_name, selected


def candidates(rel):
    """Имена, под которыми результат может лежать в compressed."""
    return {rel, os.path.join(os.path.dirname(rel), expected_name(os.path.basename(rel)))}


def main():
    months = sys.argv[1:]
    dirs = ([os.path.join(SRC, m) for m in months] if months
            else sorted(glob.glob(f'{SRC}/*/')))
    missing_all = []
    print(f"{'месяц':9} {'ожидалось':>10} {'есть':>8} {'НЕ ХВАТАЕТ':>11}  статус")
    for d in dirs:
        ym = os.path.basename(d.rstrip('/'))
        if not os.path.isdir(d):
            print(f'{ym:9} нет каталога в originals')
            continue
        files = selected(d)
        dst = os.path.join(DST, ym)
        miss = []
        for f in files:
            rel = os.path.relpath(f, d)
            if not any(os.path.exists(os.path.join(dst, n))
                       for n in candidates(rel)):
                miss.append(f)
        imported = os.path.exists(os.path.join(dst, '.import-complete'))
        if not os.path.isdir(dst):
            status = 'каталога compressed нет'
        elif miss and imported:
            status = 'импортирован, compressed подчищен'
        elif miss:
            status = 'НЕПОЛНЫЙ'
        elif imported:
            status = 'полный, импортирован'
        else:
            status = 'полный, не импортирован'
        print(f'{ym:9} {len(files):10d} {len(files)-len(miss):8d} '
              f'{len(miss):11d}  {status}')
        missing_all += miss
    if missing_all:
        with open('/tmp/compressed-missing.lst', 'w') as fh:
            fh.write('\n'.join(missing_all) + '\n')
        print(f'\nсписок недостающих: /tmp/compressed-missing.lst '
              f'({len(missing_all)})')


if __name__ == '__main__':
    main()
