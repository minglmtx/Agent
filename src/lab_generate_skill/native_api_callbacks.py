"""API callbacks for the existing formal native method.

No launcher, qualification, claim, export or retry policy is introduced here.
The trusted outer must bind a formal source and its original native
owner/guard/closure before calling this adapter. No local pilot is promoted.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import re

from lab_generate_skill.generator_observation import require_context_fit
from lab_generate_skill.generator_sft import fingerprint
from lab_generate_skill.native_training import (
    NativeTrainingValidator, callback_pin, require, run_native_training_task,
)
from lab_generate_skill.stage1_budget import CreditGuard
from lab_generate_skill.stage1_services import ResponseCache

IDENTITY_FORMAT = 'identity_full_teacher_messages_v1'


def projected_teacher_input(messages, key):
    """One request containing required fields and shared, complete page texts."""
    from .teacher_evidence_projection import GUIDE, project, serialized, unique
    selected = teacher_messages(messages, key)
    payload, audit = project(json.loads(messages[1]['content'], object_pairs_hook=unique))
    selected[0]['content'] += GUIDE
    selected[1]['content'] = serialized(payload)
    return selected, audit


def readable_teacher_messages(messages, key):
    return projected_teacher_input(messages, key)[0]


def teacher_input_contract():
    """Bind the readable template when constructing a NEW frozen source plan.

    Old source plans and their cached requests are never silently upgraded.
    The caller still owns qualification, freezing and source authorization.
    """
    from .native_training import pin
    from .teacher_evidence_projection import VERSION, project
    return dict(teacher_input_format=VERSION,
        teacher_input_processor=pin(__file__),
        teacher_projection_implementation=pin(project.__code__.co_filename))


def teacher_processor(plan):
    """Resolve the same declared processor for sending and independent review."""
    from .teacher_evidence_projection import VERSION, project
    mode = plan.get('teacher_input_format', IDENTITY_FORMAT)
    require(mode in (IDENTITY_FORMAT, VERSION), 'Unknown Teacher input format')
    processor = readable_teacher_messages if mode == VERSION else teacher_messages
    callback_pin(processor, plan['teacher_input_processor'])
    if mode == VERSION:
        callback_pin(project, plan['teacher_projection_implementation'])
    else:
        require('teacher_projection_implementation' not in plan,
                'Projection implementation requires an explicit readable format')
    return processor


def teacher_messages(messages, key):
    """The exact existing method input, without encoding, selection or clipping."""
    require(re.fullmatch(r'teacher-[1-3]', key) is not None, 'Unexpected Teacher key')
    require(isinstance(messages, list) and len(messages) == 2
            and [m.get('role') for m in messages] == ['system', 'user']
            and all(isinstance(m.get('content'), str) for m in messages),
            'Expected the existing complete Teacher message pair')
    return deepcopy(messages)


def save_same(path, value):
    """Preserve first evidence; resume may only confirm identical content."""
    path = Path(path)
    if path.exists():
        require(path.is_file() and not path.is_symlink()
                and fingerprint(json.loads(path.read_text())) == fingerprint(value),
                'Existing Teacher input changed')
        return
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


class NativeAPIRequests:
    """Connect actual backends to the original cache and paid credit guard.

    Backends and the live catalog are supplied by the trusted future launcher:
    TransformersChatBackend for Generator; OpenAIChatBackend for Teacher.
    Test doubles can exercise this boundary without creating either model/API.
    """
    def __init__(self, *, validator, directory, generator, teacher,
                 generator_tokenizer, catalog):
        require(isinstance(validator, NativeTrainingValidator), 'Formal native validator required')
        self.validator = validator
        self.plan = validator.plan
        self.source = validator.contract['source_task_id']
        self.task = dict(task_id=validator.contract['task_id'], domain=validator.contract['domain'])
        validator.validate_context(self.task, purpose='training')
        self.processor = teacher_processor(self.plan)
        self.directory = Path(directory).resolve()
        require(str(self.directory) == self.plan['result_directory'], 'Formal result directory differs')
        require(catalog.get('id') == self.plan['teacher_settings']['model'], 'Teacher catalog model differs')
        self.generator, self._teacher = generator, teacher
        self.tokenizer = generator_tokenizer
        self.check_backend(generator, self.plan['generator_settings'])
        self.check_backend(teacher, self.plan['teacher_settings'])
        self.cache = ResponseCache(self.directory / 'requests',
            validator.authorization['teacher_cost_stop_usd'], guard=CreditGuard(deepcopy(catalog)))

    @staticmethod
    def check_backend(backend, settings):
        require(backend.model_name == settings['model']
                and backend.settings.model_dump(mode='json') == settings,
                'Actual backend differs from formal source settings')

    def generate(self, messages, seed, temperature, key):
        match = re.fullmatch(r'bootstrap-([0-3])-([0-4])', key)
        require(match is not None, 'Unexpected Generator key')
        candidate, retry = map(int, match.groups())
        require(seed == 42 + candidate + retry * 4
                and temperature == min(1.2, .7 + .1 * retry), 'Original Generator schedule changed')
        self.validator.validate_context(self.task, purpose='training')
        previous_temperature = self.generator.settings.temperature
        try:
            self.generator.settings.temperature = temperature
            settings = dict(self.plan['generator_settings'], temperature=temperature)
            self.check_backend(self.generator, settings)
            require_context_fit(self.tokenizer, messages, settings['max_input_tokens'])
            return self.cache.call([self.source, key], messages, self.generator, seed, paid=False)
        finally:
            self.generator.settings.temperature = previous_temperature

    def teacher(self, messages, seed, key):
        require(re.fullmatch(r'teacher-[1-3]', key) is not None, 'Unexpected Teacher key')
        require(seed == 42 + int(key.rsplit('-', 1)[1]) - 1, 'Original Teacher seed changed')
        self.validator.validate_context(self.task, purpose='training')
        self.check_backend(self._teacher, self.plan['teacher_settings'])
        actual = self.directory / (key + '-actual-input.json')
        ledger = self.cache.directory / (fingerprint([self.source, key]) + '.json')
        # Never manufacture an actual-input sidecar for an older completed or
        # ambiguous request. The first attempt saves it before any preflight.
        if self.processor is readable_teacher_messages:
            from .native_training import pin
            from .teacher_evidence_projection import VERSION
            raw_path = self.directory / (key + '-raw-input.json')
            require(not ledger.exists() or (actual.exists() and raw_path.exists()),
                    'Existing Teacher ledger has no original input')
            save_same(raw_path, dict(messages=messages, seed=seed, source_plan=self.validator.source_plan_ref))
            selected, audit = projected_teacher_input(messages, key)
            save_same(actual, dict(messages=selected, seed=seed, input_processing=VERSION,
                raw_input=pin(raw_path), projection_audit=audit,
                raw_messages_sha256=fingerprint(messages), source_plan=self.validator.source_plan_ref))
        else:
            require(not ledger.exists() or actual.exists(), 'Existing Teacher ledger has no original input')
            selected = self.processor(messages, key)
            save_same(actual, dict(messages=selected, seed=seed,
                input_processing=IDENTITY_FORMAT, raw_messages_sha256=fingerprint(messages),
                source_plan=self.validator.source_plan_ref))
        # CreditGuard uses the selected API catalog context, not the local
        # Qwen 36,864 limit. ResponseCache retains full input on preflight pause.
        return self.cache.call([self.source, key], selected, self._teacher, seed, paid=True)


def run_with_native_api(*, validator, directory, generator, teacher,
                        generator_tokenizer, catalog, get_start, retrieve, rollout):
    """Run the unchanged formal stage machine using a separately qualified owner.

    get_start/retrieve/rollout must come from the caller's frozen qualified
    source, with its original initial guard and source-bound native reviewer.
    A result here is not a closed-source audit or a released training export.
    """
    requests = NativeAPIRequests(validator=validator, directory=directory,
        generator=generator, teacher=teacher, generator_tokenizer=generator_tokenizer,
        catalog=catalog)
    return run_native_training_task(requests.task, requests.directory / 'stage1',
        validator=validator, get_start=get_start, retrieve=retrieve, rollout=rollout,
        generate=requests.generate, teacher=requests.teacher,
        model_info=dict(generator=generator.model_name, actor='Qwen2.5-7B-Instruct',
                        teacher=teacher.model_name, teacher_mode='authorized_api',
                        bank_sha256=validator.plan['bank']['sha256']))
