"""Frozen current location catalog and its imported direct dependency closure."""
from pathlib import Path
import importlib
import json
from map_route_location import catalog

class RouteLocationCatalog(catalog.RouteLocationCatalog):
    def __init__(self,config,*,project):
        if Path(catalog.__file__).resolve()!=Path(project).resolve()/'scripts/map_route_location/catalog.py':
            raise ValueError('Only current frozen location code may supply proofs')
        super().__init__(config,project=project)

def required_runtime_files(project):
    project=Path(project).resolve()
    if Path(catalog.__file__).resolve()!=project/'scripts/map_route_location/catalog.py':
        raise ValueError('Current frozen location package required')
    review=json.loads((project/'scripts/map_route_location/offline-review.json').read_text())
    files=set()
    for row in review['direct_runtime_files']:
        path=Path(row['path']);package=path.parent.name
        name=(package+'.'if package in ('lab_generate_skill','map_routes','map_surfaces')else'')+path.stem
        actual=Path(importlib.import_module(name).__file__).resolve()
        try:relative=actual.relative_to(project).as_posix()
        except ValueError:raise ValueError('Location dependency outside frozen project')
        files.add(relative)
    # All peer packages are part of the current capsule, including indirect
    # archive/observer readers; accepting only the direct import list is insufficient.
    for package in ('map_routes','map_surfaces'):
        files.update(p.relative_to(project).as_posix()for p in (project/'scripts'/package).glob('*.py')if not p.name.startswith('test_'))
    return files
