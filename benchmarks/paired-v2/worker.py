"""Shared evaluation adapter. Original Agent loops and tool implementations remain separate."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

NAMES = {'read_file', 'write_file', 'edit_file', 'list_files', 'grep_search', 'run_shell'}
SYSTEM = ('You are a Python coding assistant. Complete the requested task in the current working directory. '
          'Read the instructions and source before editing. Use the provided tools to inspect files, implement the solution, '
          'and run the provided tests. Only change the permitted solution file. Do not alter tests or retrieve external solutions. '
          'Report actual test results; do not claim a test passed unless you ran it successfully. '
          'Tools operate in the task directory; networking and access to other tasks are disabled.')


def append(path, value):
    with path.open('a') as f:
        f.write(json.dumps(value, default=str) + '\n')
        f.flush()


async def main(config):
    out = Path(config['output'])
    state = out / 'state'
    state.mkdir()
    (state / 'tool-results').mkdir()
    tool_state = out / 'tool-state'
    tool_state.mkdir()
    os.environ.update(MINI_CLAUDE_STATE_DIR=str(state), MINI_CLAUDE_DISABLE_MEMORY='1',
                      MINI_CLAUDE_CONTEXT_WINDOW='16384', MINI_CLAUDE_MAX_OUTPUT_TOKENS='2048',
                      MINI_CLAUDE_LOCAL_MODEL='1', MINI_CLAUDE_SDK_MAX_RETRIES='0',
                      MINI_CLAUDE_TOKENIZER=config['tokenizer'])
    sys.path.insert(0, config['source_python'])
    os.chdir(config['workspace'])
    import mini_claude.agent as module
    import mini_claude.session as sessions
    sessions.SESSION_DIR = state / 'sessions'  # baseline's old fixed path; same isolation for both
    agent = module.Agent(model='qwen3-8b-local', api_base=config['endpoint'], api_key='local-benchmark',
                         permission_mode='bypassPermissions', max_turns=(11 if config['variant'] == 'baseline' else 10), custom_system_prompt=SYSTEM,
                         custom_tools=[t for t in module.tool_definitions if t['name'] in NAMES])
    agent.effective_window = 16384 - 2048 - 256
    agent._mcp_initialized = True
    agent._start_memory_prefetch_for_turn = lambda *args: None
    agent._consume_memory_prefetch_if_ready = lambda *args: None
    agent._openai_client.max_retries = 0
    original_create = agent._openai_client.chat.completions.create
    request_no = 0

    async def create(**kw):
        nonlocal request_no
        request_no += 1
        number = request_no
        kw['max_tokens'] = 2048
        kw['temperature'] = 0
        kw['seed'] = 20261109
        kw['extra_body'] = {'chat_template_kwargs': {'enable_thinking': False}}
        start = time.monotonic()
        append(out / 'requests.jsonl', {'event': 'dispatch', 'id': number, 'request': kw})
        try:
            response = await original_create(**kw)
        except BaseException as exc:
            append(out / 'requests.jsonl', {'event': 'error', 'id': number, 'error': repr(exc), 'seconds': time.monotonic()-start})
            raise
        if not kw.get('stream'):
            append(out / 'requests.jsonl', {'event': 'completed', 'id': number, 'usage': response.usage.model_dump() if response.usage else None,
                                          'seconds': time.monotonic()-start, 'response': response.model_dump()})
            return response
        async def stream():
            usage, complete = None, False
            try:
                async for chunk in response:
                    if chunk.usage:
                        usage = chunk.usage.model_dump()
                    yield chunk
                complete = True
            finally:
                await response.close()
                append(out / 'requests.jsonl', {'event': 'completed' if complete else 'unknown', 'id': number,
                                              'usage': usage, 'seconds': time.monotonic()-start})
        return stream()
    agent._openai_client.chat.completions.create = create

    async def execute(name, inp, read_state=None):
        if name not in NAMES:
            return f'Error: tool {name} not available in this evaluation.'
        inp = dict(inp)
        if name == 'run_shell':
            inp['timeout'] = min(float(inp.get('timeout', 30000)), 60000)
        payload = dict(name=name, input=inp, read_state=dict(read_state or {}), source_python=config['source_python'],
                       workspace=config['workspace'], tool_state=str(tool_state), tool_results=str(state / 'tool-results'))
        child_env = {k: v for k, v in os.environ.items() if k in ('PATH', 'LD_LIBRARY_PATH', 'LANG', 'LC_ALL', 'PYTHONDONTWRITEBYTECODE', 'PYTHONPATH', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS')}
        child_env.update(MINI_CLAUDE_STATE_DIR=str(tool_state), TMPDIR=config['workspace'])
        p = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name('tool_child.py')),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=child_env, start_new_session=True)
        start = time.monotonic()
        append(out / 'tools.jsonl', {'event': 'start', 'pid': p.pid, 'name': name, 'input': inp})
        try:
            stdout, stderr = await asyncio.wait_for(p.communicate(json.dumps(payload).encode()), timeout=75)
        except BaseException:
            try: os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: await asyncio.wait_for(p.wait(), 5)
            except asyncio.TimeoutError:
                try: os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                await p.wait()
            raise
        if p.returncode:
            raise RuntimeError(f'tool transport failed ({p.returncode}): {stderr.decode()[-4000:]}')
        reply = json.loads(stdout)
        if read_state is not None:
            read_state.update(reply['read_state'])
        append(out / 'tools.jsonl', {'event': 'complete', 'pid': p.pid, 'name': name, 'result': reply['result'], 'seconds': time.monotonic()-start})
        return reply['result']
    module.execute_tool = execute  # preserves journal wrapping and selected version's tool handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, agent.abort)
    started = time.monotonic()
    metadata = dict(variant=config['variant'], task=config['task'], status='started', tool_round_budget=10, configured_max_turns=agent.max_turns)
    try:
        result = await asyncio.wait_for(agent.run_once(config['prompt']), timeout=570)
        inferred = 'aborted' if agent._aborted else ('max_turns' if agent.current_turns > 10 else 'completed')
        metadata.update(status='returned', result=result, stop_reason=getattr(agent, 'stop_reason', inferred),
                        aborted=agent._aborted, turns=agent.current_turns)
    except BaseException as exc:
        metadata.update(status='error', error=repr(exc), traceback=traceback.format_exc())
    finally:
        metadata.update(seconds=time.monotonic()-started, compaction_events=getattr(agent, 'compaction_events', []))
        (out / 'transcript.json').write_text(json.dumps(agent._openai_messages, indent=2, default=str))
        (out / 'model.json').write_text(json.dumps(metadata, indent=2, default=str))
        await agent.close()
    return 0 if metadata['status'] == 'returned' else 2

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main(json.loads(Path(sys.argv[1]).read_text()))))
