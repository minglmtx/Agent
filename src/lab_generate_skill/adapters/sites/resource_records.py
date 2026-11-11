"""Site namespace over shared exact resource-journal fact handling."""

from lab_generate_skill.adapters.ledger.resource_facts import ResourceFacts

_records = ResourceFacts("site")
phase = _records.phase
put = _records.put
fact = _records.fact
acknowledged = _records.acknowledged

reference = _records.reference
