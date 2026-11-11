"""Teacher uses the original captured-read verifier; no dispatch or private projection."""

from .observation_read_review import review_observation_read as teacher_observation_read

__all__ = ["teacher_observation_read"]
