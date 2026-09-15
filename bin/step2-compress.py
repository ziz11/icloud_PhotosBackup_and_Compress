#!/usr/bin/env python3
"""
Шаг 2: сжатие выгруженных оригиналов в ~/PhotosBackup/compressed/<YYYY-MM>.
Оригиналы только читаются.

Правила отбора:
  - Live-половинки (видео, рядом с которым одноимённое фото) пропускаются:
    при импорте Live Photo всё равно не собирается обратно, а так не плодятся
    лишние ролики. В бэкапе они остаются.
  - Если есть <имя>_edited.<ext>, берётся отредактированная версия,
    исходник пропускается (иначе на импорте выйдет два объекта из одного).
  - XMP-сайдкар копируется рядом с результатом и переименовывается под него,
    иначе osxphotos import его не найдёт.
  - Если сжатый файл вышел не меньше оригинала — кладётся оригинал.

Без аргументов обрабатываются все месяцы. Можно ограничить список:
    step2-compress.py 2026-08
    step2-compress.py 2026-07 2026-08
"""
import os, sys, shutil, subprocess, collections
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.expanduser('~/PhotosBackup')
SRC, DST = f'{ROOT}/originals', f'{ROOT}/compressed'
IMG_Q = os.environ.get('IMG_Q', '50')
VID_Q = os.environ.get('VID_Q', '45')
JOBS  = int(os.environ.get('JOBS', '6'))

IMG_EXT  = {'.heic', '.heif', '.jpg', '.jpeg', '.png'}
VID_EXT  = {'.mov', '.mp4', '.m4v'}
COPY_EXT = {'.dng', '.cr2', '.nef', '.arw', '.webp', '.gif', '.aae'}


def source_dirs(months):
    if not months:
        return [SRC]
    dirs = []
    for m in months:
        d = os.path.join(SRC, m)
        if not os.path.isdir(d):
            sys.exit(f'нет каталога {d}')
        dirs.append(d)
    return dirs


def build_worklist(months):
    work, skipped = [], collections.Counter()
    for top in source_dirs(months):
        for root, _, files in os.walk(top):
            names = [f for f in files
                     if not f.startswith('.') and not f.endswith('.xmp')]
            stems = collections.defaultdict(set)
            for f in names:
                s, e = os.path.splitext(f)
                stems[s].add(e.lower())
            for f in names:
                stem, ext = os.path.splitext(f)
                ext = ext.lower()
                if ext in VID_EXT and (stems[stem] & IMG_EXT):
                    skipped['live-половинка'] += 1
                    continue
                if not stem.endswith('_edited') and f'{stem}_edited' in stems:
                    skipped['есть _edited'] += 1
                    continue
                work.append(os.path.join(root, f))
    return work, skipped


def run(cmd):
    return subprocess.run(cmd, capture_output=True).returncode == 0


def process(src):
    rel = os.path.relpath(src, SRC)
    stem, ext = os.path.splitext(rel)
    ext = ext.lower()
    plain = os.path.join(DST, rel)

    if ext in IMG_EXT:
        out = os.path.join(DST, stem + '.heic')
    elif ext in VID_EXT:
        out = os.path.join(DST, stem + '.mp4')
    else:
        out = plain

    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        return ('skip', 0, 0)

    if ext in IMG_EXT:
        ok = run(['sips', '-s', 'format', 'heic',
                  '-s', 'formatOptions', IMG_Q, src, '--out', out])
        if ok:
            run(['exiftool', '-overwrite_original', '-TagsFromFile', src,
                 '-all:all', '-icc_profile', out])
    elif ext in VID_EXT:
        ok = run(['ffmpeg', '-y', '-v', 'error', '-i', src,
                  '-c:v', 'hevc_videotoolbox', '-q:v', VID_Q, '-tag:v', 'hvc1',
                  '-c:a', 'copy', '-movflags', '+faststart',
                  '-map_metadata', '0', out])
    else:
        shutil.copy2(src, out)
        ok = True

    if not ok or not os.path.exists(out):
        return ('error', 0, 0)

    osz, nsz = os.path.getsize(src), os.path.getsize(out)
    if nsz >= osz:                       # сжатие не помогло — берём оригинал
        os.remove(out)
        out = plain
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy2(src, out)
        nsz = osz

    sidecar = src + '.xmp'               # подгоняем имя сайдкара под результат
    if os.path.exists(sidecar):
        shutil.copy2(sidecar, out + '.xmp')

    return ('ok', osz, nsz)


def main():
    months = sys.argv[1:]
    work, skipped = build_worklist(months)
    print(f'месяцы: {", ".join(months) if months else "все"}')
    print(f'к обработке: {len(work)} файлов')
    for k, v in skipped.items():
        print(f'  пропущено ({k}): {v}')
    print()

    stats = collections.Counter()
    osum = nsum = 0
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        for i, (st, o, n) in enumerate(ex.map(process, work), 1):
            stats[st] += 1
            osum += o
            nsum += n
            if i % 500 == 0:
                print(f'  {i}/{len(work)}  {osum/2**30:.1f} -> {nsum/2**30:.1f} GB',
                      flush=True)

    print(f'\nготово: {dict(stats)}')
    if nsum:
        print(f'{osum/2**30:.2f} GB -> {nsum/2**30:.2f} GB  '
              f'({osum/nsum:.2f}x, экономия {(osum-nsum)/2**30:.2f} GB)')


if __name__ == '__main__':
    main()
