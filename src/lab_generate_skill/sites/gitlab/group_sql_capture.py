"""Original fixed selected SQL projections in the existing read-only session.

The shared session supplies one repeatable-read snapshot, NUL framing, 20s
statement timeout and explicit close errors. No goal values are used in SQL.
The original selected-project COPY evidence remains a separate required guard.
"""

from .ssh_sql_session import SQL_SESSION

GROUP_CAPTURE = SQL_SESSION + r"""
raw=STDIN.read(8193)
raise 'native group selector byte bound' unless raw.bytesize.between?(1,8192)
input=JSON.parse(raw)
raise 'native group selector fields' unless input.is_a?(Hash) && input.keys.sort == ['task','username','with_settings'] &&
  input['username'].is_a?(String) && input['username'].match?(/\A[A-Za-z0-9_.-]+\z/) &&
  input['username'].bytesize <= 255 && [true,false].include?(input['with_settings'])
db=LabGitlabSsh::SqlSession.new
begin
  users=db.select("SELECT id,username FROM users WHERE username='"+input['username']+"'")
  raise 'one original group account required' unless users.length == 1
  groups=db.select("SELECT id,name,path,type,visibility_level,parent_id FROM namespaces WHERE type='Group' ORDER BY id")
  members=db.select("SELECT id,source_id,user_id,access_level FROM members WHERE type='GroupMember' ORDER BY id")
  settings=input['with_settings'] ? db.select("SELECT s.namespace_id,s.setup_for_company,s.jobs_to_be_done FROM namespace_settings s JOIN namespaces n ON n.id=s.namespace_id WHERE n.type='Group' ORDER BY s.namespace_id") : nil
ensure
  db.finish($!)
end
value={'schema_version'=>'gitlab-group-state/1','task'=>input['task'],'user'=>users[0],
       'groups'=>groups,'members'=>members,'settings'=>settings}
output=JSON.generate(value)
raise 'complete native group CAS byte bound' if output.bytesize > 64*1024*1024
STDOUT.write(output)
"""
