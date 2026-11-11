"""The selected original navigation identities and original private contract pins.

This declaration confers no execution or historical admission authority.
"""

from .identity import TaskIdentity
from .map_navigation_next_group import NEXT_NAVIGATION_PAGE_PINS


def check_navigation_scope(task: TaskIdentity, native_contract_sha256: str) -> None:
    selected = {
        "0189de83adbd18ca5109": (
            "0189de83adbd18ca5109--derived-fc863f3963f9",
            "0fbbc42993ddc1400edaa53927da5ebd0fc29c0b5146d9ca0544676e9b64c488",
        ),
        "058c211ed6572633b8e3": (
            "058c211ed6572633b8e3",
            "d5d6878aad1e27345967a59b1d4258750c191e3ffa07065c5ca689ff4d90fd21",
        ),
        "2117cabad5712d8d165c": (
            "2117cabad5712d8d165c--derived-7facdbc81bda",
            "f364ba41373b56c8fd420b176628fc15b6b1a67d8f681a70b18cf5d3f4a27aec",
        ),
        "227f0ce76530eca31eeb": (
            "227f0ce76530eca31eeb--derived-8a4cfe686265",
            "48ee709b51ab32ec7976d939eed6357f8fad9fe99478eeec0f53ada417b414bb",
        ),
        "54066c2710d43c3a8205": (
            "54066c2710d43c3a8205--derived-2c673681c761",
            "2fce55ecec46a8c4f4502ac91efe3d2915c93f4ddf4dc0e39d6c3b594e73e081",
        ),
        "7442ae72bc2576957ca4": (
            "7442ae72bc2576957ca4--derived-2af03c7fe57b",
            "3b27fff01cc32297d86baa9bf1f43cf4e0002e75cfb0527f6757f631a33fbbba",
        ),
        "c230980afa6f0bf0342b": (
            "c230980afa6f0bf0342b--derived-67ed09376ad7",
            "bd551f4bc3de959051b1c3059b8a448a0af7831bc63c85654469366efa2be95d",
        ),
        "eecb7b3837b34a864e11": (
            "eecb7b3837b34a864e11--derived-84b0c02519c1",
            "a5b783dd8c0e273ec414f69e202374bbb4a7c2f56b4367fa6e53ea31b0c9bafb",
        ),
        "f049bdfefc158611ea45": (
            "f049bdfefc158611ea45--derived-f9fbf16a5d2a",
            "3d381c727f23000b089cb81497315626514e06677b54b10f22725b4f298352f5",
        ),
    }
    selected.update(NEXT_NAVIGATION_PAGE_PINS)
    if (task.site, task.family, task.contract_version, task.split) != (
        "map",
        "navigation_page_identity",
        1,
        "train",
    ) or selected.get(task.source_task_id) != (task.task_id, native_contract_sha256):
        raise ValueError("Exact selected train navigation identity/contract required")


NAVIGATION_PAGE_MEMBERS = frozenset(
    (
        "0189de83adbd18ca5109",
        "2117cabad5712d8d165c",
        "227f0ce76530eca31eeb",
        "54066c2710d43c3a8205",
        "7442ae72bc2576957ca4",
        "c230980afa6f0bf0342b",
        "eecb7b3837b34a864e11",
        "f049bdfefc158611ea45",
    )
)


# Original8 remain pinned above; the next complete42 share only page semantics.
NAVIGATION_PAGE_MEMBERS = NAVIGATION_PAGE_MEMBERS | frozenset(NEXT_NAVIGATION_PAGE_PINS)


def check_page_navigation_scope(
    task: TaskIdentity, native_contract_sha256: str
) -> None:
    check_navigation_scope(task, native_contract_sha256)
    if task.source_task_id not in NAVIGATION_PAGE_MEMBERS:
        raise ValueError(
            "Only explicitly pinned complete navigation-page groups are supported"
        )
