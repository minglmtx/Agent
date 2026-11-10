"""One bounded RPC, executing the selected version's original tool function."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
from isolation import restrict, runtime_reads

async def main():
    request = json.loads(sys.stdin.read())
    sys.path.insert(0, request['source_python'])
    from mini_claude.tools import execute_tool
    work = Path(request['workspace'])
    state = Path(request['tool_state'])
    os.chdir(work)
    os.environ['MINI_CLAUDE_STATE_DIR'] = str(state)
    restrict(runtime_reads() + [sys.prefix, request['source_python'], request.get('tool_results', request['tool_state'])], [work, state, '/dev/null'])
    task = asyncio.current_task()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    read_state = request['read_state']
    try:
        result = await execute_tool(request['name'], request['input'], read_state)
        print(json.dumps({'result': result, 'read_state': read_state}))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(json.dumps({'result': f'Error: {type(exc).__name__}: {exc}', 'read_state': read_state}))

if __name__ == '__main__':
    asyncio.run(main())
