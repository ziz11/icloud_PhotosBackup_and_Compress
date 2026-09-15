#!/usr/bin/env python3
"""
Ревизия по счёту (сверка по именам ненадёжна: Photos нормализует имена
у пар вида "X.heic" / "X (1).heic").

ожидалось = уникальных по содержимому файлов в originals после правил отбора
есть      = счётчик альбома Recompressed/<месяц> из `osxphotos albums`
            (в отличие от запроса по плоскому альбому, видит и те месяцы,
             что заливались до появления флага --album "Recompressed")

Вывод: /tmp/audit-gaps.tsv — месяц <TAB> ожидалось <TAB> есть <TAB> дыра
"""
import os, re, sys, glob, hashlib, subprocess, collections

ROOT = os.path.expanduser('~/PhotosBackup')
IMG = {'.heic', '.heif', '.jpg', '.jpeg', '.png'}
VID = {'.mov', '.mp4', '.m4v'}


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


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


def albums():
    r = subprocess.run(['osxphotos', 'albums'], capture_output=True, text=True)
    got = {}
    for line in r.stdout.splitlines():
        m = re.match(r'\s*Recompressed/(\S+):\s*(\d+)', line)
        if m:
            got[m.group(1)] = int(m.group(2))
    return got


def main():
    got = albums()
    rows = []
    for p in sorted(glob.glob(f'{ROOT}/originals/*/')):
        ym = os.path.basename(p.rstrip('/'))
        files = selected(p)
        if not files:
            continue
        uniq = len({md5(f) for f in files})
        have = got.get(ym, 0)
        rows.append((ym, uniq, have, max(0, uniq - have)))

    started = [r for r in rows if r[2] > 0]
    never = [r for r in rows if r[2] == 0]
    gaps = [r for r in started if r[3] > 0]

    print(f"{'месяц':9} {'ожидалось':>10} {'есть':>7} {'дыра':>6}")
    for ym, u, h, d in gaps:
        print(f'{ym:9} {u:10d} {h:7d} {d:6d}')
    print(f"\nмесяцев обработано: {len(started)}, из них с дырами: {len(gaps)}")
    print(f"ПОТЕРЯНО в обработанных: {sum(r[3] for r in gaps)} объектов")
    print(f"ещё не начато: {len(never)} месяцев, {sum(r[1] for r in never)} объектов")
    with open('/tmp/audit-gaps.tsv', 'w') as f:
        f.write('\n'.join(f'{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}' for r in gaps) + '\n')


if __name__ == '__main__':
    main()
