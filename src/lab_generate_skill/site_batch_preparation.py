"""Bound cold paired-site preparation separately from an actual source attempt."""
import time
from .io_utils import atomic_write_json
from .runtime_watchdog import deadline_scope
from .site_walltime_guard import SourceBudget

# Based on the observed ~24 minute cold pair setup; this is a finite batch
# setup bound, not an extension of browser/model or per-source deadlines.
PAIR_SETUP_SECONDS = 1800


def pair_setup_seconds(domain):
    # Two fresh Reddit instances were measured at about 85 seconds total.
    # A ten-minute ceiling retains substantial load/I/O margin. Other sites
    # retain the existing thirty-minute cold-start bound.
    return 600 if domain == 'reddit' else PAIR_SETUP_SECONDS


def prepare_pair(sites, walltime, attempt_budget, out):
    if getattr(sites, 'pair', None) is not None:
        return {'allowed': True, 'already_prepared': True}
    setup_seconds = pair_setup_seconds(getattr(sites, 'domain', None))
    reserve = SourceBudget(setup_seconds + attempt_budget.attempt_seconds,
                           attempt_budget.cleanup_seconds, attempt_budget.safety_seconds)
    decision = walltime.check(reserve)
    if not decision['allowed']:
        return decision
    started = time.monotonic()
    report = {'stage': 'website_batch_initialization', 'timeout_seconds': setup_seconds,
              'source_claimed': False, 'model_loaded_by_preparation': False,
              'attempt_budget_unchanged': attempt_budget.record(), 'status': 'started'}
    atomic_write_json(out/'website-preparation.json', report)
    try:
        with deadline_scope('website_batch_initialization', setup_seconds):
            sites.prepare_pair()
        report['status'] = 'ready'
    except BaseException as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report['seconds'] = time.monotonic() - started
        atomic_write_json(out/'website-preparation.json', report)
    return {**decision, 'preparation': report}
