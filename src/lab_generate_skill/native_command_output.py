"""Read one completed launch from an append-only native service log."""
from pathlib import Path


def launch_log_offset(path):
    path = Path(path)
    return path.stat().st_size if path.exists() else 0


def read_launch_output(path, name, *, offset):
    """Remove only our exact launch header, never native warnings or errors.

    Callers must capture the byte offset before launching and check the command
    exit status before reading. Earlier invocations stay in the diagnostic log.
    """
    if not isinstance(name, str) or not name or '\n' in name or '\r' in name:
        raise ValueError('A single native service name is required')
    if type(offset) is not int or offset < 0:
        raise ValueError('A nonnegative pre-launch byte offset is required')
    with Path(path).open('rb') as stream:
        stream.seek(0, 2)
        if stream.tell() < offset:
            raise ValueError('Native command log was truncated after launch')
        stream.seek(offset)
        data = stream.read()
    header = ('\n--- service launch: ' + name + ' ---\n').encode()
    if not data.startswith(header):
        raise ValueError('Native command launch boundary differs')
    return data[len(header):].decode('utf-8').strip()
