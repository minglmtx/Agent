from pathlib import Path
from map_surfaces import catalog

class RemainingSurfaceCatalog(catalog.RemainingSurfaceCatalog):
    def __init__(self,*args,**kwargs):
        project=Path(__file__).resolve().parents[2]
        if Path(catalog.__file__).resolve()!=project/"scripts/map_surfaces/catalog.py":raise ValueError("Current frozen surface implementation required")
        super().__init__(*args,**kwargs)
