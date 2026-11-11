"""Fresh actual full16 terminal guard for newly produced grouped CPU evidence.

Native issue cache column changes remain completely certified by the actual
all-row witness/native renderer after the cold group, never ignored columns.
This guard additionally rejects all non-issue changes at each real terminal.
"""
from .gitlab_native_read_runtime import full_snapshot


def require_fresh_terminal(control, cycle):
    life=control.get('ordinary_lifecycle')
    if not isinstance(life,dict)or life.get('formal_lifecycle_executed')is not True or life.get('terminal_only_scoring')is not True:raise ValueError('Actual ordinary terminal lifecycle required')
    state=life.get('fresh_terminal_full16')
    if not isinstance(state,dict)or state.get('fresh_terminal_full16')is not True or state.get('columns_ignored')!=[]:raise ValueError('Fresh exact complete16 terminal snapshot required')
    before,after=state.get('before'),state.get('after')
    full_snapshot(before);full_snapshot(after)
    if before!=cycle['protected_before']:raise ValueError('Exact independently captured cold-group baseline required')
    if any(after[t]!=before[t]for t in before if t!='issues')or any(after['issues'].get(k)!=before['issues'].get(k)for k in ('rows','columns','key')):raise ValueError('Actual terminal changed protected native scope')
    if state.get('issue_all_row_cache_certification')!='deferred_to_actual_whole_cold_group_renderer':raise ValueError('Honest complete all-row issue cache certification scope required')
    if any(state.get(k)is not True for k in ('protection_certified','non_issue_tables_exact','issue_schema_rows_keys_exact')):raise ValueError('Actual terminal protection must pass')
    return True
