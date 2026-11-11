"""Bound native-reference validation by adapter cost, never by a task ID."""


def task_seconds(contract):
    # License controls load the native Rails environment for the before,
    # after, and wrong-object references. Each invocation has a 240s command
    # bound; retain independent reads, plus time for metadata and browser checks.
    if contract.get('query',{}).get('family')=='gitlab_directory_license':
        return 960
    if contract.get('query',{}).get('family')=='gitlab_tree_list':
        # Recursive native browser traversal, with independent before/after Git reads.
        return 600
    if contract.get('query',{}).get('family')=='gitlab_exact_issue_collection':
        # Paginated public scope, resolving rounded values through native issue pages.
        return 600
    return 120


def chunk_limit(contracts,requested):
    # Keep the complete cycle below 7200s, even with expensive native reads.
    return min(requested,4) if any(task_seconds(c)>120 for c in contracts) else requested
