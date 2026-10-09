#!/usr/bin/env python3
"""
Шаг 2: сжатие выгруженных оригиналов в ~/PhotosBackup/compressed/<YYYY-MM>.
Оригиналы только читаются.

Правила отбора (photolib.py):
  - Live-половинки (видео, рядом с которым одноимённое фото) пропускаются:
    при импорте Live Photo всё равно не собирается обратно, а так не плодятся
    лишние ролики. В бэкапе они остаются.
  - Если есть <имя>_edited.<ext>, берётся отредактированная версия,
    исходник пропускается (иначе на импорте выйдет два объекта из одного).
  - XMP-сайдкар копируется рядом с результатом и переименовывается под него,
    иначе osxphotos import его не найдёт.
  - Если сжатый файл вышел не меньше оригинала — кладётся оригинал.

Результат пишется во временный скрытый файл и переименовывается в конце,
поэтому прерванный прогон не оставляет «готовых» обрубков.

Без аргументов обрабатываются все полностью выгруженные месяцы
(с .export-complete). Можно ограничить список:
    step2-compress.py 2026-08
    step2-compress.py 2026-07 2026-08
"""
import collections
import glob
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from photolib import DST, IMG, SRC, VID, selected

IMG_Q = os.environ.get('IMG_Q', '50')    # HEIC качество: 50 = 2.18x @ SSIM 0.974
VID_Q = os.environ.get('VID_Q', '45')    # hevc_videotoolbox q:v: 45 = 2.19x @ PSNR 36
JOBS  = int(os.environ.get('JOBS', '6'))


def source_dirs(months):
    if not months:
        dirs = sorted(glob.glob(f'{SRC}/*/'))
        for d in dirs:
            if not os.path.exists(os.path.join(d, '.export-complete')):
                print(f'[skip] {os.path.basename(d.rstrip("/"))} не выгружен полностью')
        return [d for d in dirs if os.path.exists(os.path.join(d, '.export-complete'))]
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
        work += selected(top, skipped)
    return work, skipped


def run(cmd):
    return subprocess.run(cmd, capture_output=True).returncode == 0


def tmp_path(path):
    """Скрытое имя рядом с целью: find/импорт пропускают файлы на '.'."""
    d, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    return os.path.join(d, f'.{stem}.part{ext}')


def encode_image(src, tmp):
    if not run(['sips', '-s', 'format', 'heic', '-s', 'formatOptions', IMG_Q,
                src, '--out', tmp]):
        return False
    # добираем метаданные, которые sips мог потерять
    run(['exiftool', '-overwrite_original', '-TagsFromFile', src,
         '-all:all', '-icc_profile', tmp])
    return True


def encode_video(src, tmp):
    head = ['ffmpeg', '-y', '-v', 'error', '-i', src,
            '-c:v', 'hevc_videotoolbox', '-q:v', VID_Q, '-tag:v', 'hvc1']
    tail = ['-movflags', '+faststart', '-map_metadata', '0', tmp]
    # звук копируем; если кодек не лезет в mp4 (PCM и т.п.) — перекодируем в AAC
    return (run(head + ['-c:a', 'copy'] + tail)
            or run(head + ['-c:a', 'aac', '-b:a', '192k'] + tail))


def place(src, dst):
    """Атомарная копия: обрывок не выдаст себя за готовый файл."""
    tmp = tmp_path(dst)
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def process(src):
    rel = os.path.relpath(src, SRC)
    stem, ext = os.path.splitext(rel)
    ext = ext.lower()
    plain = os.path.join(DST, rel)

    if ext in IMG:
        out = os.path.join(DST, stem + '.heic')
    elif ext in VID:
        out = os.path.join(DST, stem + '.mp4')
    else:
        out = plain

    # plain есть — значит, сжатие уже не помогло и лежит оригинал
    if os.path.exists(out) or os.path.exists(plain):
        return ('skip', 0, 0, rel)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = tmp_path(out)
    try:
        if ext in IMG:
            ok = encode_image(src, tmp)
        elif ext in VID:
            ok = encode_video(src, tmp)
        else:
            shutil.copy2(src, tmp)
            ok = True
        if not ok or not os.path.exists(tmp):
            return ('error', 0, 0, rel)

        osz, nsz = os.path.getsize(src), os.path.getsize(tmp)
        keep = nsz < osz or not (ext in IMG or ext in VID)   # прочее — просто копия
        final = out if keep else plain

        # сайдкар раньше медиафайла: файл без сайдкара не должен выглядеть готовым
        sidecar = src + '.xmp'
        if os.path.exists(sidecar):
            place(sidecar, final + '.xmp')

        if keep:
            os.replace(tmp, final)
        else:                            # сжатие не помогло — берём оригинал
            place(src, final)
            nsz = osz
        return ('ok', osz, nsz, rel)
    except OSError as e:
        return ('error', 0, 0, f'{rel}: {e}')
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    months = sys.argv[1:]
    work, skipped = build_worklist(months)
    print(f'месяцы: {", ".join(months) if months else "все выгруженные"}')
    print(f'к обработке: {len(work)} файлов')
    for k, v in skipped.items():
        print(f'  пропущено ({k}): {v}')
    print()

    stats = collections.Counter()
    errors = []
    osum = nsum = 0
    with ThreadPoolExecutor(max_workers=JOBS) as ex:
        for i, (st, o, n, rel) in enumerate(ex.map(process, work), 1):
            stats[st] += 1
            osum += o
            nsum += n
            if st == 'error':
                errors.append(rel)
                print(f'  ERR {rel}', flush=True)
            if i % 500 == 0:
                print(f'  {i}/{len(work)}  {osum/2**30:.1f} -> {nsum/2**30:.1f} GB',
                      flush=True)

    print(f'\nготово: {dict(stats)}')
    if nsum:
        print(f'{osum/2**30:.2f} GB -> {nsum/2**30:.2f} GB  '
              f'({osum/nsum:.2f}x, экономия {(osum-nsum)/2**30:.2f} GB)')
    if errors:
        print(f'ошибок: {len(errors)} — повторный запуск обработает только их')
        sys.exit(1)


if __name__ == '__main__':
    main()
