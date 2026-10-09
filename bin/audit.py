#!/usr/bin/env python3
"""
Ревизия: что из originals не доехало до альбома Recompressed.

Работает без compressed — тот мог быть удалён. Ожидаемое имя объекта
в библиотеке вычисляется из оригинала по правилам сжатия:
    фото  -> <stem>.heic
    видео -> <stem>.mp4
    прочее (RAW и т.п.) -> имя без изменений

Правила отбора те же, что были при сжатии (см. photolib.py).

Вывод: /tmp/audit-missing.tsv  —  месяц <TAB> путь в originals <TAB> ожидаемое имя
Ложные срабатывания возможны на парах дубликатов (X и X (1) дают один объект);
они безвредны — повторная заливка такого файла отсеется как дубль.
"""
import collections
import glob
import os

from photolib import SRC, album_index, expected_name, selected


def main():
    dirs = sorted(glob.glob(f'{SRC}/*/'))
    months = [os.path.basename(p.rstrip('/')) for p in dirs]
    idx = album_index(months)
    print(f'в альбомах Recompressed/<месяц>: '
          f'{sum(sum(c.values()) for c in idx.values())} объектов\n')
    rows = []
    out = []
    for p, ym in zip(dirs, months):
        files = selected(p)
        if not files:
            continue
        have = idx.get(ym, collections.Counter())
        miss = []
        seen = collections.Counter()
        for f in files:
            want = expected_name(os.path.basename(f))
            seen[want] += 1
            if seen[want] > have.get(want, 0):
                miss.append((f, want))
        rows.append((ym, len(files), sum(have.values()), len(miss)))
        for f, want in miss:
            out.append(f'{ym}\t{f}\t{want}')

    print(f"{'месяц':9} {'ожидалось':>10} {'в альбоме':>10} {'НЕ ХВАТАЕТ':>11}")
    te = th = tm = 0
    for ym, e, h, m in rows:
        te += e; th += h; tm += m
        if m:
            print(f'{ym:9} {e:10d} {h:10d} {m:11d}')
    print(f"\nмесяцев {len(rows)}, с недостачей {sum(1 for r in rows if r[3])}")
    print(f'ожидалось {te}, в альбомах {th}, НЕ ХВАТАЕТ {tm}')
    with open('/tmp/audit-missing.tsv', 'w') as fh:
        fh.write('\n'.join(out) + ('\n' if out else ''))
    print('\nсписок: /tmp/audit-missing.tsv')


if __name__ == '__main__':
    main()
