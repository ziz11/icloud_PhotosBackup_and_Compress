#!/usr/bin/env python3
"""
Общее для скриптов пайплайна: правила отбора, ожидаемые имена, сверка с Photos.

Правила отбора (одни на сжатие, проверку и ревизию):
  - видео рядом с одноимённым фото (половинка Live Photo) пропускается;
  - исходник пропускается, если есть его _edited-версия.

CLI (для shell-скриптов):
  photolib.py uniq <каталог>   число уникальных по содержимому отобранных файлов
"""
import collections
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = os.path.expanduser('~/PhotosBackup')
SRC, DST = f'{ROOT}/originals', f'{ROOT}/compressed'
ALBUM = 'Recompressed'
IMG = {'.heic', '.heif', '.jpg', '.jpeg', '.png'}
VID = {'.mov', '.mp4', '.m4v'}


def select_names(files):
    """Имена одного каталога -> (отобранные, Counter причин пропуска)."""
    names = [f for f in files
             if not f.startswith('.') and not f.lower().endswith('.xmp')]
    stems = collections.defaultdict(set)
    for f in names:
        s, e = os.path.splitext(f)
        stems[s].add(e.lower())
    out, skipped = [], collections.Counter()
    for f in names:
        stem, ext = os.path.splitext(f)
        if ext.lower() in VID and stems[stem] & IMG:
            skipped['live-половинка'] += 1
        elif not stem.endswith('_edited') and f'{stem}_edited' in stems:
            skipped['есть _edited'] += 1
        else:
            out.append(f)
    return out, skipped


def selected(top, skipped=None):
    """Пути отобранных файлов под top (рекурсивно)."""
    out = []
    for root, _, files in os.walk(top):
        names, sk = select_names(files)
        if skipped is not None:
            skipped.update(sk)
        out += [os.path.join(root, f) for f in names]
    return out


def expected_name(fname):
    """Имя результата сжатия: фото -> .heic, видео -> .mp4, прочее как есть."""
    stem, ext = os.path.splitext(fname)
    e = ext.lower()
    if e in IMG:
        return stem + '.heic'
    if e in VID:
        return stem + '.mp4'
    return fname


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def count_unique(paths):
    """Число уникальных по содержимому файлов.
    Хешируются только файлы с совпадающим размером — остальные заведомо уникальны."""
    by_size = collections.defaultdict(list)
    for p in paths:
        by_size[os.path.getsize(p)].append(p)
    return sum(1 if len(g) == 1 else len({md5(p) for p in g})
               for g in by_size.values())


def is_recompressed(albums):
    """Объект — наша сжатая копия: лежит в плоском или помесячном альбоме.
    Только по плоскому нельзя: ранние месяцы заливались без него."""
    return any(a == ALBUM or a.startswith(ALBUM + '/') for a in albums or [])


def query(*args):
    """osxphotos query --json; при сбое — выход, а не молчаливый пустой список."""
    r = subprocess.run(['osxphotos', 'query', '--json', *args],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        sys.exit(f'osxphotos query {" ".join(args)}: не удалось прочитать ответ\n'
                 f'{r.stderr.strip()[-500:]}')


def album_index(months):
    """{месяц: Counter(original_filename)} по альбомам Recompressed/<месяц>."""
    args = []
    for m in months:
        args += ['--album', f'{ALBUM}/{m}']
    idx = collections.defaultdict(collections.Counter)
    if not args:
        return idx
    for a in query(*args):
        for al in a.get('albums') or []:
            if al.startswith(ALBUM + '/'):
                idx[al.split('/', 1)[1]][a.get('original_filename')] += 1
    return idx


def restart_photos():
    subprocess.run(['pkill', '-f', 'osxphotos import'], capture_output=True)
    time.sleep(1)
    subprocess.run(['osascript', '-e', 'tell application "Photos" to quit'],
                   capture_output=True)
    time.sleep(4)
    subprocess.run(['pkill', '-x', 'Photos'], capture_output=True)
    time.sleep(3)
    subprocess.run(['open', '-g', '-a', 'Photos'], capture_output=True)
    time.sleep(20)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'uniq':
        print(count_unique(selected(sys.argv[2])))
    else:
        sys.exit(__doc__)
