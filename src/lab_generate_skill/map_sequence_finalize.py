"""Reset native Map ID sequences without treating sentinel ID 0 as an ID to issue."""

TABLES = ('current_nodes', 'current_ways', 'current_relations', 'users', 'changesets')


def sequence_sql(table):
    if table not in TABLES:
        raise ValueError('Unknown native Map sequence table')
    # max(id) uses the primary-key index. Do not count or scan the whole table.
    # An empty table and a table containing only sentinel IDs both need the
    # sequence minimum on the *next* call (is_called=false).
    return f"""WITH source AS (SELECT max(id) AS high FROM {table}),
        sequence AS (SELECT seqrelid, seqmin FROM pg_sequence
            WHERE seqrelid=pg_get_serial_sequence('{table}','id')::regclass)
        SELECT setval(seqrelid, GREATEST(COALESCE(high,seqmin),seqmin),
                      COALESCE(high >= seqmin,false))
        FROM source CROSS JOIN sequence;"""


def finalize(session):
    for table in TABLES:
        value = session.query(sequence_sql(table))
        if not value or not value.isdigit() or int(value) < 1:
            raise ValueError(f'Native sequence initialization missing for {table}')
    session.query("UPDATE users SET data_public=false WHERE display_name='' AND data_public=true;")
