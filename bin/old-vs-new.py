#!/usr/bin/env python3
"""
Сверка перед удалением: сколько в библиотеке СТАРЫХ и сколько НОВЫХ
объектов по каждому месяцу.

Новые  — те, что лежат в альбоме Recompressed или Recompressed/<месяц>
         (наши сжатые копии; ранние месяцы есть только в помесячном альбоме).
Старые — все остальные, не считая общих альбомов iCloud (они квоту не едят).

Числа из колонки СТАРЫХ должны совпасть с тем, что покажет умный альбом
в Photos. Не совпало — не удалять, разбираться. Типичная причина:
объекты есть только в Recompressed/<месяц>, а умный альбом «не Recompressed»
считает их старыми — такие месяцы сначала добить в плоский альбом
(fix-album.py / import-robust.sh, они ставят оба альбома через --dup-albums).

  old-vs-new.py            все месяцы
  old-vs-new.py 2021-07           один месяц
  old-vs-new.py 2021-07 2022-01   только диапазон
"""
import collections
import sys

from photolib import is_recompressed, query

lo = sys.argv[1] if len(sys.argv) > 1 else '0000-00'
hi = sys.argv[2] if len(sys.argv) > 2 else (lo if len(sys.argv) > 1 else '9999-99')

old = collections.Counter(); new = collections.Counter()
for a in query('--not-shared'):
    ym = (a.get('date') or '')[:7]
    if not ym or ym < lo or ym > hi:
        continue
    (new if is_recompressed(a.get('albums')) else old)[ym] += 1

print(f"{'месяц':9} {'СТАРЫХ':>8} {'новых':>7} {'всего':>7}")
to=tn=0
for ym in sorted(set(old) | set(new)):
    o, n = old[ym], new[ym]
    to += o; tn += n
    print(f"{ym:9} {o:8d} {n:7d} {o+n:7d}")
print(f"{'ИТОГО':9} {to:8d} {tn:7d} {to+tn:7d}")
print(f"\nК удалению по этому диапазону: {to} объектов.")
