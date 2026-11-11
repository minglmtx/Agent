"""Fixed selected SSH-key capture, without initialization writes or CAS admission."""

import json
import re
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_input_commands import NativeInputCommands
from .service_contract import GitlabServiceSpec
from .service_commands import container, RUBY
from .ssh_sql_session import SQL_SESSION
from .ssh_sql_capture import SQL_CAPTURE
from .ssh_refs_capture import REFS_CAPTURE
from .tasks.ssh_key_spec import SshKeySpec
from .tasks.ssh_key_state import SshKeyNativeState

CAPTURE = SQL_SESSION + SQL_CAPTURE + REFS_CAPTURE + r"""
raw=STDIN.read(8193)
raise 'native selector byte bound' unless raw.bytesize.between?(1,8192)
input=JSON.parse(raw)
raise 'native selector fields' unless input.is_a?(Hash) && input.keys.sort == ['task','username'] &&
  input['username'].is_a?(String) && input['username'].match?(/\A[A-Za-z0-9_.-]+\z/) && input['username'].bytesize <= 255
db=LabGitlabSsh::SqlSession.new
begin
  users=LabGitlabSsh.table(db,'users'); keys=LabGitlabSsh.table(db,'keys')
  accounts=users['rows'].select{|r|r['username']==input['username']}
  raise 'one original ordinary active account required' unless accounts.length==1 && accounts[0]['admin']==false &&
    accounts[0]['state']=='active' && [true,false].include?(accounts[0]['external'])
  account=accounts[0].select{|k,v|['id','username','admin','external','state'].include?(k)}
  guard=LabGitlabSsh.guard(db,account['id'])
ensure
  db.finish($!)
end
value={'schema_version'=>'gitlab-ssh-key-state/1','task'=>input['task'],'account'=>account,
       'users'=>users,'keys'=>keys,'guard'=>guard,'refs'=>LabGitlabSsh.refs}
output=JSON.generate(value)
raise 'complete native CAS byte bound' if output.bytesize > 64*1024*1024
STDOUT.write(output)
"""


class GitlabSshNativeReader:
    def __init__(
        self, services: GitlabServiceSpec, commands: NativeInputCommands
    ) -> None:
        self.services = GitlabServiceSpec.model_validate(services)
        self.commands = commands
        self.captured_raw: bytes | None = None

    def capture(
        self, spec: SshKeySpec, username: str, control: OperationControl
    ) -> SshKeyNativeState:
        self.captured_raw = None
        spec = SshKeySpec.model_validate(spec)
        if (
            type(username) is not str
            or not 0 < len(username) <= 255
            or re.fullmatch(r"[A-Za-z0-9_.-]+", username) is None
        ):
            raise ValueError("Original ordinary native username required")
        data = json.dumps(
            {"task": spec.task.model_dump(mode="json"), "username": username},
            separators=(",", ":"),
        ).encode()
        control.checkpoint()
        raw = self.commands.run_input(
            container(self.services) + (RUBY, "-e", CAPTURE), data, control
        )
        if type(raw) is not bytes or not 0 < len(raw) <= 64 * 1024 * 1024:
            raise ValueError("Complete native capture outside its private CAS boundary")
        self.captured_raw = raw

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in items:
                if key in result:
                    raise ValueError("Duplicate native capture field")
                result[key] = value
            return result

        def constant(value: str) -> object:
            raise ValueError("Nonfinite native capture value")

        json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        value = SshKeyNativeState.model_validate_json(raw)
        if value.task != spec.task or value.account.username != username:
            raise ValueError("Native capture changed original task/account")
        control.checkpoint()
        return value
