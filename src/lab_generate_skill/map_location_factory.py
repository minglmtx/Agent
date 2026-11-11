"""Use the exact native location factory validated by ordinary input controls."""
import json
from pathlib import Path
from map_route_location import profile

def new_site(root,logs):
    project=Path(__file__).resolve().parents[2]
    if Path(profile.__file__).resolve()!=project/'scripts/map_route_location/profile.py':
        raise ValueError('Location factory must come from this frozen project')
    contract=json.loads((project/'scripts/map_route_location/contract.json').read_text())
    profile.sources(contract)
    return profile.RouteLocationSite(root,logs,observer_contract=contract)
