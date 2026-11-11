"""Trusted registry import for the staged route proof catalog."""
from pathlib import Path
from map_routes import catalog

class RemainingRouteCatalog(catalog.RemainingRouteCatalog):
    def __init__(self, config, *, project):
        expected = Path(project).resolve()/'scripts/map_routes/catalog.py'
        if Path(catalog.__file__).resolve() != expected:
            raise ValueError('Only the frozen project route package may supply proofs')
        super().__init__(config, project=project)
