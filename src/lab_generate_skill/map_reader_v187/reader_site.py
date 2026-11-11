"""Explicit full native Map fixture with a real local reader and two diaries.

All additions precede the native reset baseline. The reader handles only its
declared endpoint; native RSS and diary responses remain served by Rails.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys

from .pipelined_site import PipelinedMapExistingAccountSite
from lab_generate_skill.map_account_observation import protected_users
from lab_generate_skill.map_reset_guard import MapStateChanged
from lab_generate_skill.io_utils import atomic_write_json as save
from .reader_ui import ReaderUI,rack_initializer
from .rss_client import LocalReader


def diary_seed(account,entries):
    payload=base64.b64encode(json.dumps(dict(email=account['email'],entries=entries)).encode()).decode()
    return '''require "json"
require "base64"
require "time"
spec=JSON.parse(Base64.strict_decode64("'''+payload+'''"))
ActiveRecord::Base.transaction do
  raise "Unexpected existing diaries" unless DiaryEntry.count.zero?
  user=User.find_by!(:email=>spec.fetch("email"))
  language=Language.find_or_create_by!(:code=>"en") { |l| l.english_name="English"; l.native_name="English" }
  spec.fetch("entries").each do |entry|
    stamp=Time.iso8601(entry.fetch("created_at"))
    DiaryEntry.create!(:user=>user,:language=>language,:title=>entry.fetch("title"),:body=>entry.fetch("body"),
      :latitude=>entry.fetch("latitude"),:longitude=>entry.fetch("longitude"),:visible=>true,:created_at=>stamp,:updated_at=>stamp)
  end
end
puts "Declared synthetic New York City and Boston native diaries initialized"
'''


class ReaderDiarySite(PipelinedMapExistingAccountSite):
    def __init__(self,root,logs,*,account,diaries):
        self.reader=None;self.reader_initial=None;self.diaries=diaries
        super().__init__(root,logs,account=account)

    def prepare_app_database(self,state,db):
        super().prepare_app_database(state,db)
        folder=self.state/'local-reader';folder.mkdir()
        self.reader_database=folder/'subscriptions.sqlite'
        LocalReader(self.reader_database,create=True)
        self.reader=ReaderUI(self.reader_database,self.url)
        self.reader_port=self.reader.start()
        source=rack_initializer(self.reader_port)
        (state/'app/config/initializers/lab_local_reader.rb').write_text(source)
        save(self.logs/'local-reader-extension.json',dict(explicit_environment_derivative=True,
             original_benchmark_equivalence=False,entry='/__lab_local__/reader',reader_port=self.reader_port,
             native_feed_interception=False,installed_before_guard=True,source_sha256=hashlib.sha256(source.encode()).hexdigest()))

    def start_frontend(self,port):
        super().start_frontend(port)
        if self.reset_guard is not None:raise ValueError('Diary fixture must precede reset baseline')
        path=self.state/'frontend/app/tmp/declared-local-diaries.rb'
        source=diary_seed(self.account,self.diaries);path.write_text(source)
        try:self.run(self.rails_command[:-5]+['runner','/app/tmp/'+path.name],'seed_declared_local_diaries',180)
        finally:path.unlink(missing_ok=True)
        self.account_users=protected_users(self)
        self.reader_initial=self.reader_snapshot()
        save(self.logs/'declared-local-diaries.json',dict(synthetic_content=True,original_benchmark_equivalence=False,
             records=self.diary_records(),script_sha256=hashlib.sha256(source.encode()).hexdigest()))

    def diary_records(self):
        return json.loads(self.app_sql("SELECT coalesce(json_agg(x),'[]'::json) FROM (SELECT d.id,d.title,d.body,d.latitude,d.longitude,d.visible,u.display_name AS author FROM diary_entries d JOIN users u ON u.id=d.user_id ORDER BY d.id)x"))

    def reader_snapshot(self):
        folder=self.reader_database.parent
        if sorted(p.name for p in folder.iterdir())!=['subscriptions.sqlite'] or any(p.is_symlink()for p in folder.iterdir()):
            raise ValueError('Unexpected reader persistence or journal')
        raw=self.reader_database.read_bytes()
        return dict(logical=LocalReader(self.reader_database).snapshot(),files=[dict(name='subscriptions.sqlite',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())])

    def reset_state(self):
        if self.reader_snapshot()!=self.reader_initial:
            raise MapStateChanged('Reader changed; complete cold restoration required')
        super().reset_state()

    def __exit__(self,*args):
        try:
            if self.reader is not None:
                self.reader.close();self.reader=None
        finally:super().__exit__(*args)
