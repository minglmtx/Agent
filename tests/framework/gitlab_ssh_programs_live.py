"""Fixed-image syntax/fixture gate only: no database or large seed initialization."""

from pathlib import Path
from lab_generate_skill.sites.gitlab.ssh_native_reader import CAPTURE
from lab_generate_skill.sites.gitlab.ssh_sql_session import SQL_SESSION
from lab_generate_skill.sites.gitlab.ssh_sql_capture import SQL_CAPTURE
from lab_generate_skill.sites.gitlab.ssh_refs_capture import REFS_CAPTURE
from gitlab_programs_live import native, RUBY
from site_instance_fixtures import node_path as node_path


def test_selected_reader_programs_compile_with_original_ruby(node_path: Path) -> None:
    for name in ("state", "control", "snapshot"):
        (node_path / name).mkdir()
    for program in (SQL_SESSION, SQL_CAPTURE, REFS_CAPTURE, CAPTURE):
        assert native(node_path, (RUBY, "-c", "-e", program)) == b"Syntax OK\n"
    assert not list((node_path / "state").iterdir())


def test_sql_traversal_runs_complete_small_fixture_and_refuses_bad_rows(
    node_path: Path,
) -> None:
    for name in ("state", "control", "snapshot"):
        (node_path / name).mkdir()
    program = "require 'json'; require 'digest'\n" + SQL_CAPTURE + r"""
class Fake
  attr_accessor :broken
  def select(sql)
    return [{'column_name'=>'id','data_type'=>'integer'}] if sql.include?('information_schema.columns')
    return [{'n'=>2}] if sql.include?('COUNT(*)')
    return [{'names'=>['id']}] if sql.include?('pg_index')
    if sql.include?('row_to_json(t) AS row')
      return [{'row'=>{'id'=>1}},{'row'=>{'id'=>@broken ? 1 : 2}}]
    end
    return [{'digest'=>'a'*32,'native_key'=>[1]},{'digest'=>'b'*32,'native_key'=>[@broken ? 1 : 2]}] if sql.include?('md5(')
    raise 'unexpected SQL'
  end
end
db=Fake.new
value=LabGitlabSsh.table(db,'keys')
raise 'incomplete rows' unless value['complete'] && value['rows']==[{'id'=>1},{'id'=>2}]
guard=LabGitlabSsh.guard(db,1)
raise 'incomplete tables' unless guard.keys==LabGitlabSsh::TABLES
expected=Digest::SHA256.hexdigest('a'*32+"\n"+'b'*32+"\n")
raise 'hash differs' unless guard.values.all?{|v|v['sha256']==expected && v['rows']==2}
db.broken=true
[lambda{LabGitlabSsh.table(db,'keys')},lambda{LabGitlabSsh.guard(db,1)}].each do |call|
  rejected=false
  begin;call.call;rescue RuntimeError;rejected=true;end
  raise 'bad native traversal accepted' unless rejected
end
puts 'complete-and-bad-fixtures-checked'
"""
    assert (
        native(node_path, (RUBY, "-e", program))
        == b"complete-and-bad-fixtures-checked\n"
    )
