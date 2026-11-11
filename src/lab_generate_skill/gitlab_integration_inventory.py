"""Read safe integration metadata across native GitLab schema versions.

This is capability evidence, not a task answer: project permissions, inherited
settings and the user-visible interface still need independent verification.
Encrypted properties and credentials must never be selected.
"""
from .site_database import select_rows


def metadata_query(schema):
    tables = {}
    for row in schema:
        if row.get('table_name') in ('integrations', 'services'):
            tables.setdefault(row['table_name'], set()).add(row['column_name'])
    table = next((t for t in ('integrations', 'services') if t in tables), None)
    if table is None:
        raise ValueError('Native integration metadata table unavailable; not an empty result')
    columns = tables[table]
    if not {'id', 'project_id', 'active'} <= columns:
        raise ValueError('Incomplete native integration identity/status columns')
    # GitLab renamed the STI discriminator to type_new. All identifiers below
    # are code-owned literals; metadata cannot introduce SQL identifiers.
    kind = next((c for c in ('type_new', 'type') if c in columns), None)
    if kind is None:
        raise ValueError('Native integration type column unavailable; not an empty result')
    optional = [c for c in ('group_id', 'instance', 'inherit_from_id') if c in columns]
    selected = ['id', 'project_id', 'active', kind + ' AS integration_type', *optional]
    query = ('SELECT ' + ','.join(selected) + ' FROM ' + table
             + ' WHERE lower(' + kind + ") LIKE '%github%' ORDER BY id")
    return {'table': table, 'type_column': kind, 'sql': query}


def read_metadata(site, schema):
    declaration = metadata_query(schema)
    return {**declaration, 'rows': select_rows(site, declaration['sql']),
            'status': 'read_completed', 'task_reference_verified': False}
