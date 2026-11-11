"""Read original saved objects and complete bounded native write-scope rows."""
from pathlib import Path
import base64, hashlib, json
from uuid import uuid4
from .save_judge import snapshot
from .save_protection import ROW_TABLES
from lab_generate_skill.map_reset_guard import STATE_SQL, checked_state, persistent_files
from lab_generate_skill.io_utils import atomic_write_json as save

HERE = Path(__file__).parent


def source():
    original = (HERE / 'native_snapshot.rb').read_text()
    sql = base64.b64encode(STATE_SQL.encode()).decode()
    tables = json.dumps(ROW_TABLES)
    extra = '''
  rows = {}
  TABLES.each do |name|
    values = JSON.parse(ActiveRecord::Base.connection.select_value("SELECT coalesce(json_agg(x), '[]'::json)::text FROM (SELECT t.* FROM public.#{name} t ORDER BY to_jsonb(t)::text LIMIT 5001) x"))
    raise "Native write inventory exceeds 5000 rows" if values.length > 5000
    rows[name] = values
  end
  users_protected = JSON.parse(ActiveRecord::Base.connection.select_value("SELECT coalesce(json_agg(x), '[]'::json)::text FROM (SELECT id, md5((to_jsonb(users)-'traces_count'-'diary_entries_count')::text) AS protected_sha, traces_count, diary_entries_count FROM users ORDER BY id LIMIT 1001) x"))
  raise "Native user inventory exceeds 1000 rows" if users_protected.length > 1000
  guard = ActiveRecord::Base.connection.select_value(Base64.strict_decode64("SQL"))
  guard = JSON.parse(guard) if guard.is_a?(String)
  result[:protection] = { :guard => guard, :rows => rows, :users => users_protected }
'''.replace('TABLES', tables).replace('SQL', sql)
    assert original.count('end\nputs JSON.generate(result)') == 1
    return 'require "base64"\n' + original.replace('end\nputs JSON.generate(result)', extra + 'end\nputs JSON.generate(result)')


def capture(site, directory, label):
    directory = Path(directory)
    code = source().encode()
    ident = 'save-snapshot-' + uuid4().hex
    path = site.state / 'frontend/app/tmp' / (ident + '.rb')
    path.write_bytes(code)
    command = site.rails_command[:-5] + ['runner', '/app/tmp/' + path.name]
    try:
        site.run(command, ident, 180)
    finally:
        path.unlink(missing_ok=True)
    log = site.logs / (ident + '.log')
    values = [json.loads(line) for line in log.read_text().splitlines() if line.startswith('{') and '"read_only"' in line]
    if len(values) != 1:
        raise ValueError('Exactly one native readonly snapshot required')
    value = snapshot(values[0])
    checked_state(value['protection']['guard'])
    files = json.loads(json.dumps(persistent_files(site.state / 'frontend/app')))
    save(directory / (label + '.json'), value)
    save(directory / (label + '-files.json'), files)
    # Keep the raw native readout inside the evidence package, rather than an
    # absolute log pointer that will disappear with the owned environment.
    raw = log.read_bytes()
    (directory / (label + '.log')).write_bytes(raw)
    save(directory / (label + '-receipt.json'), dict(read_only=True, command=command,
        source_sha256=hashlib.sha256(code).hexdigest(), raw_sha256=hashlib.sha256(raw).hexdigest(),
        bounded_tables=ROW_TABLES, all_public_table_triggers=True))
    return value, files
