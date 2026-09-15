#!/usr/bin/env python3
"""
Чинит членство в альбоме, не гоняя месяц целиком.

Случай: объект импортирован в библиотеку, но выпал из альбома Recompressed
(обычно из-за таймаута AppleScript при добавлении в альбом). Точечно такие
не находятся через --check-not: osxphotos считает файл импортированным.

Здесь список подозреваемых строится по именам: если файлов с ожидаемым
именем на диске больше, чем объектов с таким original_filename в альбоме,
файл попадает в кандидаты. Сверка по именам не доказательство (Photos
нормализует имена у пар вида "X.heic" / "X (1).heic"), но как список
кандидатов годится: лишний кандидат безвреден, его отсеет --skip-dups,
а --dup-albums всё равно допишет объект в альбом.

  fix-album.py 2024-02
  fix-album.py 2024-02 --dry-run
"""
import collections
import json
import os
import subprocess
import sys
import time

CHUNK = int(os.environ.get('CHUNK', '8'))
TIMEOUT = int(os.environ.get('TIMEOUT', '180'))
RETRY = int(os.environ.get('RETRY', '3'))

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


def album_names(ym):
    r = subprocess.run(['osxphotos', 'query', '--album', 'Recompressed', '--json'],
                       capture_output=True, text=True)
    data = json.loads(r.stdout)
    c = collections.Counter()
    for a in data:
        if f'Recompressed/{ym}' in (a.get('albums') or []):
            c[a.get('original_filename')] += 1
    return c


def disk_names(d):
    """{ожидаемое имя: [пути]} с учётом правил отбора."""
    names = [f for f in os.listdir(d)
             if not f.startswith('.') and not f.endswith('.xmp')]
    stems = collections.defaultdict(set)
    for f in names:
        s, e = os.path.splitext(f)
        stems[s].add(e.lower())
    out = collections.defaultdict(list)
    for f in names:
        stem, ext = os.path.splitext(f)
        if ext.lower() in VID and (stems[stem] & IMG):
            continue
        if not stem.endswith('_edited') and f'{stem}_edited' in stems:
            continue
        out[expected_name(f)].append(os.path.join(d, f))
    return out


def import_chunk(files, ym):
    for attempt in range(1, RETRY + 1):
        p = subprocess.Popen(
            ['osxphotos', 'import', *files, '--skip-dups', '--dup-albums',
             '--sidecar', '--album', 'Recompressed', '--album', f'Recompressed/{ym}'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            out, _ = p.communicate(timeout=TIMEOUT)
            return out
        except subprocess.TimeoutExpired:
            p.kill()
            print(f'    таймаут (попытка {attempt}) — перезапуск Photos', flush=True)
            restart_photos()
    return None


def main():
    ym = sys.argv[1]
    dry = '--dry-run' in sys.argv
    d = os.path.expanduser(f'~/PhotosBackup/compressed/{ym}')
    if not os.path.isdir(d):
        sys.exit(f'нет папки {d}')

    have = album_names(ym)
    disk = disk_names(d)

    cand = []
    for name, paths in disk.items():
        short = len(paths) - have.get(name, 0)
        if short > 0:
            cand.extend(paths[:short])

    print(f'[{ym}] файлов на диске {sum(len(v) for v in disk.values())}, '
          f'в альбоме {sum(have.values())}, кандидатов {len(cand)}')
    for p in sorted(cand)[:20]:
        print('   ', os.path.basename(p))
    if dry or not cand:
        return

    for i in range(0, len(cand), CHUNK):
        part = cand[i:i + CHUNK]
        restart_photos()
        out = import_chunk(part, ym)
        n = i // CHUNK + 1
        total = (len(cand) + CHUNK - 1) // CHUNK
        if out is None:
            print(f'  [FAIL] чанк {n}/{total}')
        else:
            line = [l for l in out.splitlines() if l.startswith('Done:')]
            print(f'  чанк {n}/{total} — {line[-1] if line else "?"}', flush=True)

    after = album_names(ym)
    print(f'[{ym}] в альбоме стало {sum(after.values())}')


if __name__ == '__main__':
    main()
