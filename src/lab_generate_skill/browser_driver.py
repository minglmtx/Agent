"""Borrow BrowserGym's live driver for setup; retain owned standalone lifecycle.

Each initializer still creates/closes its own browser and context. Borrowing
the driver never shares actor pages, cookies, storage or task state.
"""
from contextlib import contextmanager


@contextmanager
def initialization_playwright():
    import browsergym.core as core
    from playwright.sync_api import sync_playwright
    active=getattr(core,'_PLAYWRIGHT',None)
    if active is not None:
        yield active
    else:
        with sync_playwright() as owned:
            yield owned
