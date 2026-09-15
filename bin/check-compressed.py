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
import os, sys, glob, collections

ROOT = os.path.expanduser('~/PhotosBackup')
SRC, DST = f'{ROOT}/originals', f'{ROOT}/compressed'
IMG = {'.heic', '.heif', '.jpg', '.jpeg', '.png'}
VID = {'.mov', '.mp4', '.m4v'}


def selected(d):
    out = []
    for root, _, files in os.walk(d):
        names = [f for f in files
                 if not f.startswith('.') and not f.endswith('.xmp')]
        stems = collections.defaultdict(set)
        for f in names:
            s, e = os.path.splitext(f)
            stems[s].add(e.lower())
        for f in names:
            stem, ext = os.path.splitext(f)
            if ext.lower() in VID and (stems[stem] & IMG):
                continue
            if not stem.endswith('_edited') and f'{stem}_edited' in stems:
                continue
            out.append(os.path.join(root, f))
    return out


def candidates(rel):
    """Имена, под которыми результат может лежать в compressed."""
    stem, ext = os.path.splitext(rel)
    e = ext.lower()
    names = [rel]
    if e in IMG:
        names.append(stem + '.heic')
    elif e in VID:
        names.append(stem + '.mp4')
    return names


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
