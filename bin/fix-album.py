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
import os
import subprocess
import sys

from photolib import DST, album_index, expected_name, restart_photos, selected

CHUNK = int(os.environ.get('CHUNK', '8'))
TIMEOUT = int(os.environ.get('TIMEOUT', '180'))
RETRY = int(os.environ.get('RETRY', '3'))


def disk_names(d):
    """{ожидаемое имя: [пути]} с учётом правил отбора."""
    out = collections.defaultdict(list)
    for p in selected(d):
        out[expected_name(os.path.basename(p))].append(p)
    return out


def import_chunk(files, ym):
    for attempt in range(1, RETRY + 1):
        p = subprocess.Popen(
            ['osxphotos', 'import', *files, '--skip-dups', '--dup-albums',
             '--sidecar', '--album', 'Recompressed', '--album', f'Recompressed/{ym}'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            out, _ = p.communicate(timeout=TIMEOUT)
            if p.returncode == 0:
                return out
            print(f'    код {p.returncode} (попытка {attempt})', flush=True)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            print(f'    таймаут (попытка {attempt}) — перезапуск Photos', flush=True)
            restart_photos()
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 1:
        sys.exit(__doc__)
    ym = args[0]
    dry = '--dry-run' in sys.argv
    d = os.path.join(DST, ym)
    if not os.path.isdir(d):
        sys.exit(f'нет папки {d}')

    have = album_index([ym])[ym]
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

    after = album_index([ym])[ym]
    print(f'[{ym}] в альбоме стало {sum(after.values())}')


if __name__ == '__main__':
    main()
