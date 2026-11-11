"""Bounded parallel full13 checks for quiescent test-only Reddit instances.

No cached table digests and no sampled rows. Preserve the published checksum
algorithms and output schema. Call only before browser creation or after every
browser context has closed; this is not a concurrent-writer snapshot protocol.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace


def complete_snapshot(site, out, *, browser_contexts_closed=False):
    if browser_contexts_closed is not True:
        raise ValueError('Parallel protection requires a quiescent instance with all browser contexts closed')
    if site.domain != 'reddit':
        raise ValueError('Native Reddit test instance required')
    from .reddit_exact_forum_runtime import TABLES, HEAVY_TABLES, _small_digest_query
    from .reddit_protected_chunks import full_digest, validate_snapshot
    from .reddit_native_read_protection import VERSION
    from .reddit_submission_snapshot_stream import submission_snapshot
    from .site_database import select_rows
    import re

    names = ','.join("'" + name + "'" for name in TABLES)
    present = select_rows(site, "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN (" + names + ') ORDER BY table_name')
    if len(present) != 12 or {row.get('table_name') for row in present} != set(TABLES):
        raise ValueError('Every original protected table must exist')
    small = tuple(name for name in TABLES if name not in HEAVY_TABLES)
    rows = select_rows(site, _small_digest_query(small))
    if (len(rows) != len(small) or {r.get('table_name') for r in rows} != set(small)
            or any(type(r.get('count')) is not int or r['count'] < 0
                   or not isinstance(r.get('digest'), str) or not re.fullmatch('[0-9a-f]{32}', r['digest']) for r in rows)):
        raise ValueError('Complete small-table protection required')
    task_tables = {r['table_name']:dict(count=r['count'],digest=r['digest']) for r in rows}
    # Comments and users dominate the serial scan. Each uses its unchanged
    # bounded PK scanner and fresh read-only REPEATABLE READ transaction.
    groups = [('comments',), tuple(name for name in HEAVY_TABLES if name != 'comments')]
    log_root = Path(out).with_suffix('')
    log_root.mkdir(parents=True, exist_ok=False)
    def heavy(index, tables):
        logs = log_root / ('scan-' + str(index)); logs.mkdir()
        proxy = SimpleNamespace(domain=site.domain, base=list(site.base), db_port=site.db_port,
                                logs=logs, command=site.command)
        return full_digest(proxy, list(tables), timeout=150)
    with ThreadPoolExecutor(max_workers=3) as pool:
        scans = [pool.submit(heavy, i, tables) for i,tables in enumerate(groups)]
        submissions = pool.submit(submission_snapshot, site, out)
        for future in scans:
            value = future.result()
            if set(task_tables) & set(value): raise ValueError('Duplicate protected table')
            task_tables.update(value)
        submission_result = submissions.result()
    validate_snapshot(task_tables)
    return dict(version=VERSION, twelve_task_tables=task_tables,
                submissions=submission_result, users_only_ignored_column='last_seen')
