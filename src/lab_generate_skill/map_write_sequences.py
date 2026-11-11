"""Calibrate restored native allocators before admitting writes to a fresh site.

Run only before Rails starts, on the disposable restored database. Never lower
an allocator or change object rows. Indexed maxima avoid geographic scans.
"""
import json
from .map_sequence_finalize import TABLES


def repair_sql(table):
    if table not in TABLES:
        raise ValueError('Unknown native sequence table')
    return f"""CREATE OR REPLACE FUNCTION pg_temp.calibrate_native_allocator()
    RETURNS json LANGUAGE plpgsql AS $$
    DECLARE s regclass; last_id bigint; used boolean; high bigint;
    BEGIN
      s := pg_get_serial_sequence('{table}', 'id')::regclass;
      IF s IS NULL THEN RAISE EXCEPTION 'Missing native sequence'; END IF;
      SELECT max(id) INTO high FROM {table};
      EXECUTE format('SELECT last_value,is_called FROM %s',s) INTO last_id,used;
      IF high IS NOT NULL AND (high > last_id OR (high = last_id AND NOT used)) THEN
        PERFORM setval(s,high,true);
      END IF;
      EXECUTE format('SELECT last_value,is_called FROM %s',s) INTO last_id,used;
      RETURN json_build_object('table','{table}','max_id',high,
        'sequence',s::text,'last_value',last_id,'is_called',used);
    END $$;
    SELECT pg_temp.calibrate_native_allocator();
    """


def calibrate(site):
    rows = []
    for table in TABLES:
        # psql prints command tags; JSON is the final line. No nextval probe.
        row = json.loads(site.app_sql(repair_sql(table)).splitlines()[-1])
        if getattr(site, 'logs', None) is not None:
            from .io_utils import atomic_write_json
            atomic_write_json(site.logs/'native-write-sequence-progress.json',
                              dict(completed=rows, current=row))
        if row.get('table') != table or not row.get('sequence'):
            raise ValueError('Missing native allocator observation')
        high, last = row.get('max_id'), row.get('last_value')
        called = row.get('is_called')
        if type(last) is not int or type(called) is not bool:
            raise ValueError('Exact native sequence state unavailable')
        if high is not None and (type(high) is not int or type(last) is not int or last < high or (last == high and not called)):
            raise ValueError('Native allocator remains behind restored objects')
        rows.append(row)
    return dict(version='native-write-sequences-v2', tables=rows,
                object_rows_changed=False, before_website_start=True)
