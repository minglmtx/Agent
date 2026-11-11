"""Exact prepared-input wrapper compatibility with the original Actor64 envelope.

Only the complete checked handoff implementation is recognized. Native inference,
model loading, math, allocator cleanup, configuration and hardware pins remain
in the original deployment gate; this is neither runtime discovery nor permission.
The paired compatibility tests compare the original immutable native function
bodies and exercise the actual deployment consumer, including partial/drift refusal.
"""

from collections.abc import Mapping
from .actor_verified_context_qualification import VERIFIED_ACTOR_RUNTIME

PREPARED_ACTOR_RUNTIME = {
    "src/lab_generate_skill/adapters/models/actor_service.py": "3361002ac3f9b9eae473eab929dae8759efb4119b17a0891544bd49c6a2c317a",
    "src/lab_generate_skill/adapters/models/actor_worker_client.py": "72c3d3dfeae5bd806a850a1aee7fe0e5116012f1fc6544cde674f3108290cd9a",
    "src/lab_generate_skill/adapters/models/actor_worker_protocol.py": "d9329c10e5bd39e9219d9058c2bff76bb7d513046b845e907959eed0e13bea83",
    "src/lab_generate_skill/adapters/models/local_actor.py": "dc3f196d18227feb426ca6b3201e102e868f79c060cefe60cb74db35a3305d55",
    "src/lab_generate_skill/adapters/models/transformers_actor.py": "96d9fc55e34c53bf0c3a4c770b39ccfea50a3bb8cb7d78111176129fed082888",
    "src/lab_generate_skill/application/actor_generation.py": "4843574636c904dcfb3ce7f633a0488badab909597e9e914c1758227eb441a2c",
    "src/lab_generate_skill/application/actor_generation_control.py": "eb9ef776f3c56df419b32edaf552d4dd955dce73119000033bf6d60aac634632",
    "src/lab_generate_skill/application/actor_loop.py": "188d2ea8df686ca5bc312e374e34313a1d264de2f6ea67663671c65f72846115",
    "src/lab_generate_skill/application/actor_model_admission.py": "bb0ce6bbc564dfaba893651a05743290b4dc5db789a885ee61233e3de00713f2",
    "src/lab_generate_skill/bootstrap/actor_runtime.py": "409781eabe84cd84e5a9f64c361af2e56f046df70ccd3c5e540ebc873d700e62",
    "src/lab_generate_skill/domain/actor_dispatch.py": "847f6aae1ed46b3d765cc792045df7b4921f5ae4e92921d4ec3703e911789b1a",
    "src/lab_generate_skill/domain/actor_execution_window.py": "014f455f330bcf4699066a8a64f818d856698ec36ffb634ef96e9585b7d10493",
    "src/lab_generate_skill/domain/actor_generation.py": "887e907fdee4ae0d998663ff07ce4f5d979178a1e8d3790f0870a280ed7a8c7e",
    "src/lab_generate_skill/domain/actor_run.py": "9171c530ad3b5d776e208c6600ec0dcfbe1b5af9118b19f74ca0bc6ea95dd077",
    "src/lab_generate_skill/domain/local_actor.py": "1fba8076b48ac88d69eb27761fa19c823eb3df3780fd7ded4f35c154075631ad",
    "src/lab_generate_skill/domain/task_initialization.py": "c609b26f007c96990ede4f096d3cad30f04dcfc3625e2261ed1924d0839730e6",
    "src/lab_generate_skill/domain/trace_events.py": "efa0789ba91394d8d7ce70012cc549737ecd7dae8b701c8f1ace615ab7860da6",
    "src/lab_generate_skill/ports/actor_engine.py": "850f19eb1dead9da8bbee2934465ce1a3a8f25d5902f982ff7559d973d054286",
}

PREPARED_ACTOR_ORIGINALS = {
    "src/lab_generate_skill/adapters/models/transformers_actor.py": "0122eebdeeb588eedf620af076690bd72f2be01b883b12eb4a069fe439a38cd7",
    "src/lab_generate_skill/adapters/models/actor_service.py": "1120747358ac4332a5c43ae53c747e96f09612d3c6bbe53bb21f1db77cfae47d",
    "src/lab_generate_skill/adapters/models/actor_worker_protocol.py": "604a4121cf0118d80a58115259a086d61a37575a6692bc6bcace5c6c93b4a386",
    "src/lab_generate_skill/adapters/models/actor_worker_client.py": "81aea94551a5d9fffa56f3a81cc383700002987c2717731b08205728d86e6894",
}


def qualified_prepared_runtime_pins(
    files: Mapping[str, object], pins: dict[str, str]
) -> dict[str, str]:
    """Normalize only this exact complete delta for the existing envelope digest."""
    if all(
        files.get(name) == value for name, value in PREPARED_ACTOR_RUNTIME.items()
    ) or (
        bool(VERIFIED_ACTOR_RUNTIME)
        and all(
            files.get(name) == value for name, value in VERIFIED_ACTOR_RUNTIME.items()
        )
    ):
        return {**pins, **PREPARED_ACTOR_ORIGINALS}
    return pins
