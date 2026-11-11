"""Small published tree fixtures; image declarations retain real pins, no fake SIFs."""

import hashlib
import json
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.map_runtime_inputs import (
    IMAGE_PINS,
    MapRuntimeImage,
    MapRuntimeInputs,
    MapRuntimeTree,
)

ROUTING_SUFFIXES = "mldgr ramIndex names ebg_nodes timestamp geometry cell_metrics properties edges icd enw tls partition turn_weight_penalties cnbg_to_ebg datasource_names cnbg nbg_nodes turn_duration_penalties tld maneuver_overrides ebg cells fileIndex turn_penalties_index restrictions".split()


def pin(path: Path) -> ReleaseFile:
    body = path.read_bytes()
    return ReleaseFile(
        path=path.name,
        sha256=hashlib.sha256(body).hexdigest(),
        size_bytes=len(body),
        executable=False,
    )


def save(path: Path, value: Any) -> ReleaseFile:
    path.write_text(json.dumps(value))
    return pin(path)


def runtime_case(root: Path) -> MapRuntimeInputs:
    workspace = root / "workspace"
    workspace.mkdir()
    images = tuple(
        MapRuntimeImage.model_validate(
            dict(
                role=role,
                source_path=str(workspace / role / (role + ".sif")),
                file=ReleaseFile(
                    path=role + ".sif", sha256=sha, size_bytes=size, executable=False
                ),
            )
        )
        for role, (sha, size) in IMAGE_PINS.items()
    )
    leaves = {
        "app": [
            "baseline.json",
            "postgres/PG_VERSION",
            "postgres/global/pg_control",
            "empty.lock",
        ],
        "search": ["stage.json", "postgres/PG_VERSION", "postgres/global/pg_control"],
        "routing": [
            "stage.json",
            "files.jsonl",
            *(
                f"{p}/us-northeast-latest.osrm.{s}"
                for p in ("car", "bike", "foot")
                for s in ROUTING_SUFFIXES
            ),
        ],
        "tiles": ["stage.json", "postgres/PG_VERSION", "postgres/global/pg_control"],
        "frontend": [
            "Gemfile.lock",
            "app/assets/javascripts/index.js",
            "app/assets/javascripts/leaflet.share.js",
            "app/assets/javascripts/leaflet.layers.js",
            "vendor/assets/leaflet/leaflet.osm.js",
            "bin/native",
        ],
    }
    trees = []
    published = []
    for role, names in leaves.items():
        tree = workspace / (role + "-tree")
        tree.mkdir()
        directories = {"empty-directory"}
        rows: list[dict[str, Any]] = []
        for name in names:
            path = tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            body = b"" if name == "empty.lock" else (role + ":" + name).encode()
            path.write_bytes(body)
            mode = 0o755 if name == "bin/native" else 0o600
            path.chmod(mode)
            directories.update(str(p) for p in Path(name).parents if str(p) != ".")
            historical = "/historical-label-never-read/" + role + "/" + name
            rows.append(
                dict(
                    relative=name,
                    source=historical,
                    resolved_source=historical,
                    state=[1, 2, len(body), 3, 4, mode],
                    sha256=hashlib.sha256(body).hexdigest(),
                    bytes=len(body),
                )
            )
        (tree / "empty-directory").mkdir()
        value = dict(
            source="/historical-label-never-read/" + role,
            destination=str(tree),
            files=rows,
            directories=sorted(directories),
            excluded=["node_modules", "tmp"] if role == "frontend" else [],
            bytes=sum(row["bytes"] for row in rows),
        )
        metadata = workspace / (role + "-inventory.json")
        inventory_pin = save(metadata, value)
        trees.append(
            MapRuntimeTree.model_validate(
                dict(
                    role=role,
                    source_root=str(tree),
                    inventory_path=str(metadata),
                    inventory=inventory_pin,
                )
            )
        )
        published.append(
            dict(
                key=role,
                destination=str(tree),
                files=len(rows),
                bytes=value["bytes"],
                inventory=dict(path=str(metadata), sha256=inventory_pin.sha256),
                seconds=0.0,
            )
        )
    receipt = workspace / "publication.json"
    receipt_pin = save(
        receipt,
        dict(
            passed=True,
            job_id="12345",
            trees=published,
            source_deletions=0,
            source_changes=0,
            services_started=0,
            model_calls=0,
            seconds=0.0,
        ),
    )
    web = next(image for image in images if image.role == "web")
    return MapRuntimeInputs(
        files=SiteFilesPlan(
            instance_id="map-fixture",
            workspace_root=str(workspace),
            source_path=web.source_path,
            image=web.file,
            node_root=str(root / "instance"),
        ),
        images=images,
        trees=tuple(trees),
        publication_path=str(receipt),
        publication=receipt_pin,
        publication_job_id="12345",
    )
