"""One explicit, qualified native fixture for the two local reader sources."""
from copy import deepcopy
from pathlib import Path
import json

SOURCES = {'cb16efd063fc41a3f9d5', '40cd6ea96d1b834eddfc'}
VERSION = 'native-reader-diary-profile-v187'


def declared_profile():
    return dict(version=VERSION, **json.loads((Path(__file__).parent / 'public-environment.json').read_text()))


def validate_profile(value):
    if value != declared_profile():
        raise ValueError('Exact declared empty-reader and synthetic-diary fixture required')
    return deepcopy(value)


def profile_for_contracts(contracts):
    if not contracts or any(c.get('domain') != 'map' or c.get('source_task_id') not in SOURCES for c in contracts):
        raise ValueError('Dedicated two-source reader/diary manifest required')
    return {'map_reader_diaries': declared_profile()}


def new_site(root, logs, profile):
    profile = validate_profile(profile)
    from .reader_site import ReaderDiarySite
    return ReaderDiarySite(root, logs, account=profile['account'], diaries=profile['diaries'])
