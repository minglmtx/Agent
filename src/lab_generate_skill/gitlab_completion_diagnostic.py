"""Bounded private schema/data diagnosis; never an answer or admission oracle."""
from .site_database import select_rows


def inspect_completion(site, project_id=186, project_path='byteblaze/a11y-syntax-highlighting'):
    if type(project_id) is not int or project_id <= 0:
        raise ValueError('Explicit native project ID required')
    identity = select_rows(site, "SELECT p.id,r.path FROM projects p JOIN routes r "
        "ON r.source_id=p.id AND r.source_type='Project' WHERE p.id="+str(project_id))
    if identity != [{'id': project_id, 'path': project_path}]:
        raise ValueError('Diagnostic project identity differs')
    columns = select_rows(site, "SELECT column_name,data_type FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='merge_request_metrics' ORDER BY ordinal_position")
    names = {r['column_name'] for r in columns}
    report = {'project': identity[0], 'metric_columns': columns,
              'old_oracle_schema_available': {'merge_request_id','closed_at','merged_at'} <= names,
              'native_admission': False, 'reference_answer_generated': False}
    if 'merge_request_id' not in names:
        return report | {'rows': [], 'reason': 'Native metrics join key missing'}
    # JSON preserves the real schema instead of selecting assumed time fields.
    # Bounded private diagnostics must not be mistaken for a complete oracle.
    rows = select_rows(site, 'SELECT m.id,m.iid,m.state_id,to_jsonb(x) AS metrics '
        'FROM merge_requests m LEFT JOIN merge_request_metrics x ON x.merge_request_id=m.id '
        'WHERE m.target_project_id='+str(project_id)+' AND m.state_id IN (2,3) ORDER BY m.id LIMIT 1001')
    report.update(rows=rows[:1000], truncated=len(rows)>1000,
                  missing_metric_rows=sum(r['metrics'] is None for r in rows[:1000]))
    return report
