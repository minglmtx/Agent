"""Allow a control probe to reach artifact scoring after a completed download.

This does not rewrite browser feedback, retry actions, or award task success.
The terminal evaluator must still verify the saved artifact and its provenance.
"""


def completed_download_after_navigation_timeout(before, after):
    error = after.get('last_action_error', '')
    if not isinstance(error, str) or not all(part in error for part in (
        'TimeoutError: Locator.click:', 'click action done',
        'waiting for scheduled navigations to finish',
    )):
        return False
    previous_ids = {r.get('download_id') for r in before.get('downloads', [])}
    return any(
        isinstance(row.get('download_id'), int)
        and row['download_id'] not in previous_ids
        and row.get('status') == 'completed'
        and isinstance(row.get('bytes'), int) and row['bytes'] > 0
        and isinstance(row.get('sha256'), str) and len(row['sha256']) == 64
        for row in after.get('downloads', [])
    )
