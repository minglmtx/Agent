"""Explicit synthetic community fixture for isolated capability experiments.

This is not recovered Go-Browse content and is never installed automatically.
Production task admission must separately bind the fixture version and prove
full geographic reset isolation before using these records.
"""
import json
from pathlib import Path

VERSION='synthetic-local-community-v1'
GPS_PROFILE='synthetic-local-community-gps-v1'
SUPPORTED_PROFILES=(VERSION,GPS_PROFILE)
USERNAME='LocalBenchmarkMapper'
PASSWORD='LocalFixtureOnly-2026'
ENTRIES=[
    {'title':'Local fixture: checking pedestrian crossings',
     'body':'Synthetic benchmark diary. The mapper reviews pedestrian crossings and notes which locations need a future survey. This entry does not claim that real OpenStreetMap edits were made.',
     'created_at':'2023-03-30T10:00:00Z'},
    {'title':'Local fixture: reviewing park paths',
     'body':'Synthetic benchmark diary. The mapper compares park paths with survey notes and records questions for a later visit. This entry does not claim that real OpenStreetMap edits were made.',
     'created_at':'2023-03-31T10:00:00Z'},
]


def profile_for_contracts(contracts,domain):
    """Require explicit derivative provenance and a dedicated website worker."""
    profiles={c.get('map_community_fixture')for c in contracts}
    if not profiles or profiles=={None}:return None
    if domain!='map' or len(profiles)!=1 or next(iter(profiles))not in SUPPORTED_PROFILES:
        raise ValueError('Community fixture tasks require a dedicated Map manifest')
    profile=next(iter(profiles))
    for c in contracts:
        revision=c.get('environment_revision',{})
        if (revision.get('version')!=profile or revision.get('synthetic_content')is not True
                or revision.get('original_benchmark_equivalence')is not False):
            raise ValueError('Synthetic community initialization requires explicit provenance')
    return profile


def seed_source():
    payload=json.dumps({'username':USERNAME,'password':PASSWORD,'entries':ENTRIES})
    return '''require "json"
require "time"
spec = JSON.parse(<<'BENCHMARK_FIXTURE_JSON')
'''+payload+'''
BENCHMARK_FIXTURE_JSON
ActiveRecord::Base.transaction do
  raise "Community is already populated" unless DiaryEntry.count.zero? && Trace.count.zero?
  raise "Fixture account already exists" if User.where(:display_name => spec.fetch("username")).exists?
  language = Language.find_or_create_by!(:code => "en") { |l| l.english_name = "English"; l.native_name = "English" }
  stamp = Time.iso8601("2023-03-01T00:00:00Z")
  user = User.new(:display_name => spec.fetch("username"), :email => "local-benchmark-mapper@example.org",
                 :email_confirmation => "local-benchmark-mapper@example.org",
                 :pass_crypt => spec.fetch("password"), :pass_crypt_confirmation => spec.fetch("password"),
                 :creation_time => stamp, :data_public => true, :email_valid => true,
                 :terms_agreed => stamp, :terms_seen => true, :tou_agreed => stamp,
                 :description => "Synthetic local benchmark account; not a real community contributor.")
  user.save!
  user.confirm!
  spec.fetch("entries").each do |entry|
    t = Time.iso8601(entry.fetch("created_at"))
    DiaryEntry.create!(:user => user, :language => language, :title => entry.fetch("title"),
                       :body => entry.fetch("body"), :created_at => t, :updated_at => t, :visible => true)
  end
end
puts "Synthetic local community fixture created via native models"
'''


def install(site):
    if not site.state.is_relative_to(Path(site.temporary.name)):
        raise ValueError('An isolated temporary website instance is required')
    if site.rails_command[-5]!='server':raise ValueError('Native Rails command changed')
    path=site.state/'frontend/app/tmp/local-community-fixture.rb'
    path.write_text(seed_source())
    site.run(site.rails_command[:-5]+['runner','/app/tmp/local-community-fixture.rb'],'seed_local_community_fixture',180)


def records(site):
    return json.loads(site.app_sql("""SELECT json_build_object(
      'users',(SELECT json_agg(x ORDER BY x.id) FROM
        (SELECT id,display_name,status,data_public,email_valid,diary_entries_count FROM users WHERE display_name='LocalBenchmarkMapper')x),
      'entries',(SELECT json_agg(x ORDER BY x.id) FROM
        (SELECT d.id,u.display_name,d.title,d.body,d.created_at,d.visible FROM diary_entries d JOIN users u ON u.id=d.user_id)x),
      'trace_count',(SELECT count(*) FROM gpx_files));"""))
