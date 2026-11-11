from pathlib import Path
from map_surfaces import adapters

class RemainingSurfaceAdapter(adapters.RemainingSurfaceAdapter):
    def __init__(self,*args,**kwargs):
        project=Path(__file__).resolve().parents[2]
        if Path(adapters.__file__).resolve()!=project/"scripts/map_surfaces/adapters.py":raise ValueError("Current frozen surface implementation required")
        super().__init__(*args,**kwargs)
