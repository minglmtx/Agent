"""Resume exact OSM current-table population without global EXCEPT sorts.

Requires an isolated recovered database: no website or other writer runs here.
Every range commits only after exact comparison; a timed-out transaction rolls
back. Journals describe completed work, never substitute for database recovery.
"""
import hashlib
import json
import time

from .map_current_tables import (PROJECTIONS, comparison_sql, insert_sql, insert_missing_sql,
                                 next_key_sql, projection, require_equal,
                                 require_target_key)


def completed_original_tables(before_backup):
    """Accept only the original builder's committed, fully compared prefix."""
    logs = before_backup['committed_table_logs']
    result = {}
    for name in PROJECTIONS:
        outputs = {}
        for prefix in ('populate_', 'expected_', 'actual_', 'full_row_equality_'):
            log = logs.get(prefix + name + '.log')
            if log is None:
                break
            if hashlib.sha256(log['text'].encode()).hexdigest() != log['sha256']:
                raise ValueError('Original committed-table log changed')
            lines = [x.strip() for x in log['text'].splitlines() if x.strip()]
            outputs[prefix] = lines[-1] if lines else None
        if len(outputs) != 4:
            break
        if (outputs['populate_'] != 'COMMIT' or outputs['full_row_equality_'] != 'f'
                or outputs['expected_'] != outputs['actual_']
                or not str(outputs['actual_']).isdigit()):
            raise ValueError('Original table was not completely committed and verified')
        result[name] = {'rows': int(outputs['actual_']),
                        'whole_row_projection_equal': True,
                        'validation': 'original_full_exact_comparison_in_physical_checkpoint'}
    return result


def key_sql(name):
    p = projection(name)
    return f"""SELECT json_build_object('columns',
       (SELECT json_agg(a.attname ORDER BY k.ordinality)
        FROM unnest(i.indkey) WITH ORDINALITY k(attnum,ordinality)
        JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum),
       'primary',i.indisprimary,'valid',i.indisvalid,'ready',i.indisready)
       FROM pg_index i WHERE i.indrelid='{p.target}'::regclass AND i.indisprimary;"""


class WorkBudgetEnded(RuntimeError):
    pass


class CurrentTableStatistics:
    """Keep planner estimates fresh without analyzing after every small range.

    One coordinator owns this object and session. Call observe under the
    builder's shared callback lock, after the worker has committed its range.
    ANALYZE updates optimizer statistics only; exact row comparison is unchanged.
    """

    def __init__(self, session, record):
        self.session = session
        self.record = record
        self.tables = {}

    def _refresh(self, name, reason):
        target = projection(name).target  # Only fixed, declared native tables.
        started = time.monotonic()
        self.session.query(f'ANALYZE {target};')
        estimate = int(self.session.query(
            f"SELECT reltuples::bigint FROM pg_class WHERE oid='{target}'::regclass;"))
        if estimate < 0:
            raise ValueError('ANALYZE did not produce a usable table estimate')
        self.tables[name] = dict(added=0, threshold=max(1_000_000, estimate // 4))
        self.record(dict(table=name, reason=reason, estimated_rows=estimate,
                         seconds=time.monotonic() - started,
                         next_added_rows=self.tables[name]['threshold']))

    def initialize(self, names):
        for name in dict.fromkeys(names):
            if name not in self.tables:
                self._refresh(name, 'restored_checkpoint')

    def observe(self, row):
        state = self.tables[row['table']]
        # Rechecking an already populated range does not grow the table.
        if not row['committed'] or not row['exact_equal'] or not row['inserted']:
            return
        state['added'] += row['rows']
        if state['added'] >= state['threshold']:
            self._refresh(row['table'], 'committed_growth')


def dependency_levels(pieces, completed):
    """Keep native parent/child inserts ordered while parallelizing ranges."""
    dependencies = {
        'current_node_tags': {'current_nodes'},
        'current_way_tags': {'current_ways'},
        'current_way_nodes': {'current_ways', 'current_nodes'},
        'current_relation_tags': {'current_relations'},
        'current_relation_members': {'current_relations'},
    }
    pending = list(pieces); done = set(completed); levels = []
    if not done.issubset(PROJECTIONS) or any(p[0] not in PROJECTIONS for p in pending):
        raise ValueError('Unknown current-table dependency')
    while pending:
        ready = [p for p in pending if dependencies.get(p[0], set()) <= done]
        if not ready:
            raise ValueError('Missing native parent table for remaining work')
        levels.append(ready)
        done.update(p[0] for p in ready)
        pending = [p for p in pending if p not in ready]
    return levels


def resume_table(session, name, journal, deadline, stop=None, width=100000,
                 completed_range=None, lower_bound=0, upper_bound=2**63 - 1):
    from .map_current_tables import bounds
    bounds(lower_bound, upper_bound)
    p = projection(name)
    require_target_key(name, json.loads(session.query(key_sql(name))))
    # Reject malformed negative/native overflow IDs instead of silently skipping.
    for table, col in ((p.source, p.columns[0]), (p.target, p.target_columns[0])):
        invalid = session.query(f'SELECT EXISTS(SELECT 1 FROM {table} WHERE {col}<0 '
                                f'OR {col}=9223372036854775807);')
        if invalid != 'f':
            raise ValueError('Native IDs outside declared range')
    cursor, total, blocks = lower_bound, 0, 0
    timings = []
    while True:
        if time.monotonic() >= deadline or (stop is not None and stop.is_set()):
            raise WorkBudgetEnded('Stop before the next atomic range; keep database progress')
        started = time.monotonic()
        phases = {}
        def query(phase, sql):
            began = time.monotonic()
            try:
                return session.query(sql)
            finally:
                phases[phase] = phases.get(phase, 0.) + time.monotonic() - began
        next_key = query('next_key', next_key_sql(name, cursor))
        if not next_key or int(next_key) >= upper_bound:
            return {'rows': total, 'whole_row_projection_equal': True,
                    'validation': 'bounded_union_key_ranges_exact', 'ranges': blocks,
                    'lower_bound': lower_bound, 'upper_bound': upper_bound,
                    'range_seconds': sum(timings)}
        lower = int(next_key)
        upper = min(lower + width, upper_bound)
        query('begin', 'BEGIN ISOLATION LEVEL REPEATABLE READ;')
        try:
            occupied = query('occupancy', f'SELECT EXISTS(SELECT 1 FROM {p.target} '
                                     f'WHERE {p.target_columns[0]}>={lower} '
                                     f'AND {p.target_columns[0]}<{upper});')
            if occupied == 'f':
                query('insert', insert_sql(name, lower, upper))
            elif occupied != 't':
                raise ValueError('Actual native range occupancy required')
            compared = json.loads(query('exact_compare', comparison_sql(name, lower, upper)))
            # An interrupted earlier run can end inside today's adaptive range.
            # Fill only absent primary keys; never overwrite incorrect values.
            if occupied == 't' and compared['source_rows'] > compared['target_rows']:
                query('insert_missing', insert_missing_sql(name, lower, upper))
                compared = json.loads(query('exact_compare', comparison_sql(name, lower, upper)))
            rows = require_equal(compared)
            query('commit', 'COMMIT;')
        except BaseException:
            # ON_ERROR_STOP may already have disconnected and rolled back.
            if session.process.poll() is None:
                session.query('ROLLBACK;')
            raise
        seconds = time.monotonic() - started
        row = {'table': name, 'lower': lower, 'upper': upper, 'rows': rows,
               'seconds': seconds, 'inserted': occupied == 'f',
               'exact_equal': True, 'committed': True, 'phase_seconds': phases}
        journal.write(json.dumps(row, separators=(',', ':')) + '\n')
        journal.flush()
        blocks += 1
        total += rows
        timings.append(seconds)
        cursor = upper
        if completed_range is not None:
            completed_range(row)
        # Bound each query and avoid tens of thousands of tiny round trips.
        # Adapt only range size; every key is still compared exactly once.
        if rows > 0:
            factor = min(2, max(.5, 1.5 / max(seconds, .001)))
            width = max(10000, min(2000000, int(width * factor)))
