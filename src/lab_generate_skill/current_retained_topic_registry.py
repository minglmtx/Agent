"""Lifetime owner for exact historical Topic contracts in the frozen worker.

Descriptor relocation changes only expired local paths. The original full
native merge gates and original trusted read hooks remain mandatory.
"""
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from .current_actor_entry import frozen_config, pinned_json, retained_topic_selection


def stable_descriptor(value):
    value = deepcopy(value)
    for row in value.get('original_cold_source_cycles', []):
        path = row.pop('live_path', None)
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError('Absolute original or active proof path required')
    return value


def relocated_adapter(parent, stable):
    """Keep strict original admission; resolve only exact known references."""
    class RelocatedTopicAdapter(parent):
        def _proof(self, contract, descriptor):
            source = self.exact(contract)['source_task_id']
            active = self.descriptors[source]
            if descriptor not in (stable[source], active):
                raise ValueError('Unknown retained Topic descriptor or local path')
            if stable_descriptor(descriptor) != stable_descriptor(active):
                raise ValueError('Retained Topic proof identity changed')
            return super()._proof(contract, active)
    return RelocatedTopicAdapter


class CurrentRetainedTopicRegistry:
    def __init__(self, reference, *, project, contracts, output=None):
        self.project = Path(project).resolve()
        self.contracts = deepcopy(contracts)
        self.temp = None
        self.owner = None
        self.output = Path(output).resolve() if output is not None else None
        self.closed = False
        if not sys.flags.isolated or 'PYTHONPATH' in os.environ:
            raise ValueError('Dedicated isolated Topic worker required')
        config = frozen_config(self.project)
        if retained_topic_selection(contracts, config) != reference:
            raise ValueError('Frozen current Topic registry selection differs')
        self.config = pinned_json(reference['path'], reference['sha256'])
        self.sources = {r['source_task_id']: r['contract'] for r in self.config['sources']}
        from .frozen_actor_capsule import sha, regular
        for name, expected in self.config['runtime_files'].items():
            if config['actor_submission']['files_sha256'].get(name) != expected or sha(regular(self.project, name)) != expected:
                raise ValueError('Current retained Topic runtime dependency changed')
        self.packet = Path(self.config['packet']['directory']).resolve()
        index = pinned_json(self.packet/'packet-index.json', self.config['packet']['sha256'])
        if set(index['files']) != set(self.config['packet']['members']):
            raise ValueError('Exact reviewed Topic packet members required')
        for name, record in index['files'].items():
            path = regular(self.packet, name)
            if sha(path) != record['sha256'] or path.stat().st_size != record['bytes']:
                raise ValueError('Reviewed Topic packet member differs')
        self.stable = {r['source_task_id']:r['actual_proof_descriptor'] for r in json.loads((self.packet/'proof-descriptors.json').read_text())}
        code = self.project/'scripts/native_gitlab/retained_topics'
        sys.path.insert(0, str(code))
        self.module = importlib.import_module('retained_topic_registry_v154')
        self.adapter_module = importlib.import_module('topic2_retained_adapter_v154')
        for module in (self.module, self.adapter_module):
            if Path(module.__file__).resolve().parent != code:
                raise ValueError('Foreign retained Topic runtime already loaded')
        self.partition(contracts)

    def partition(self, contracts):
        if not contracts or len({c.get('source_task_id') for c in contracts}) != len(contracts):
            raise ValueError('Distinct retained Topic contract subset required')
        for contract in contracts:
            if {k:v for k,v in contract.items() if k != 'admission_result'} != self.sources.get(contract.get('source_task_id')):
                raise ValueError('Exact retained Topic contract required')
        return [dict(rows=contracts, profile={'retained_topic_baseline': 'native-topic-baseline-v1'}, runner_arguments=[])]

    def __enter__(self):
        if self.closed or self.owner is not None:
            raise ValueError('Fresh retained Topic owner required')
        if not os.environ.get('SLURM_JOB_ID') or not os.environ.get('TMPDIR'):
            raise ValueError('Real allocation required for complete Topic proofs')
        self.temp = tempfile.TemporaryDirectory(prefix='current-retained-topic-', dir=os.environ['TMPDIR'])
        directory = Path(self.temp.name)
        self.owner = self.module.RetainedTopicRegistry(self.packet, directory/'stage', self.output or directory/'proof-report', runtime_project=self.project, allocated_execution=True)
        try:
            self.owner.stage_and_bootstrap()
            self.owner.open_proofs()
            original = self.owner.adapter
            cls = relocated_adapter(self.adapter_module.RetainedTopicAdapter, self.stable)
            adapter = cls(self.owner.rows, original.descriptors, bridge=original.bridge, resolver=original.resolver)
            dispatcher = self.owner.context.dispatcher
            dispatcher.unregister_protocol('retained_topic2_v154', original)
            self.owner.registered = False
            dispatcher.register_protocol('retained_topic2_v154', adapter)
            self.owner.adapter = adapter
            self.owner.registered = True
            return self
        except BaseException:
            self.close()
            raise

    def runner(self, argv=None, **kwargs):
        import argparse
        if self.closed or self.owner is None or self.owner.adapter is None:
            raise ValueError('Live complete Topic proof owner required')
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--manifest', type=Path, required=True)
        args, _ = parser.parse_known_args(argv)
        self.partition([json.loads(s) for s in args.manifest.read_text().splitlines() if s.strip()])
        return self.owner.runner(argv, **kwargs)

    def close(self):
        try:
            if self.owner is not None:
                self.owner.close()
        finally:
            if self.temp is not None:
                self.temp.cleanup()
                self.temp = None
            self.closed = True

    def __exit__(self, *args):
        self.close()
