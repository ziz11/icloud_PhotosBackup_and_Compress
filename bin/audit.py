#!/usr/bin/env python3
"""
Ревизия: что из originals не доехало до альбома Recompressed.

Работает без compressed — тот мог быть удалён. Ожидаемое имя объекта
в библиотеке вычисляется из оригинала по правилам сжатия:
    фото  -> <stem>.heic
    видео -> <stem>.mp4
    прочее (RAW и т.п.) -> имя без изменений

Правила отбора те же, что были при сжатии:
  - видео рядом с одноимённым фото (половинка Live Photo) не заливается
  - исходник не заливается, если есть его _edited-версия

Вывод: /tmp/audit-missing.tsv  —  месяц <TAB> путь в originals <TAB> ожидаемое имя
Ложные срабатывания возможны на парах дубликатов (X и X (1) дают один объект);
они безвредны — повторная заливка такого файла отсеется как дубль.
"""
import os, re, sys, glob, subprocess, collections, json

ROOT = os.path.expanduser('~/PhotosBackup')
IMG = {'.heic', '.heif', '.jpg', '.jpeg', '.png'}
VID = {'.mov', '.mp4', '.m4v'}


def expected_name(fname):
    stem, ext = os.path.splitext(fname)
    e = ext.lower()
    if e in IMG:
        return stem + '.heic'
    if e in VID:
        return stem + '.mp4'
    return fname


def selected(d):
    out = []
    for root, _, files in os.walk(d):
        names = [f for f in files if not f.startswith('.') and not f.endswith('.xmp')]
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


def album_index():
    """{месяц: Counter(original_filename)} из альбома Recompressed."""
    r = subprocess.run(['osxphotos', 'query', '--album', 'Recompressed', '--json'],
                       capture_output=True, text=True)
    try:
        data = json.loads(r.stdout)
    except Exception:
        print('не удалось прочитать альбом', file=sys.stderr)
        sys.exit(1)
    idx = collections.defaultdict(collections.Counter)
    for a in data:
        for al in (a.get('albums') or []):
            if al.startswith('Recompressed/'):
                idx[al.split('/', 1)[1]][a.get('original_filename')] += 1
    return idx, len(data)


def main():
    idx, total = album_index()
    print(f'в альбоме Recompressed: {total} объектов\n')
    rows = []
    out = []
    for p in sorted(glob.glob(f'{ROOT}/originals/*/')):
        ym = os.path.basename(p.rstrip('/'))
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
