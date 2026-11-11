"""Current native callback port; original runner and CPU constructors excluded."""
from lab_generate_skill.gitlab_project_description import OPERATIONS

from datetime import datetime,timezone

import base64,hashlib,json,re

from pathlib import Path

class PendingCapability(ValueError):pass

def timestamp(v):
 if not isinstance(v,str):raise ValueError('Explicit native timestamp required')
 v=v.strip().replace('Z','+00:00')
 t=datetime.fromisoformat(v)
 if t.tzinfo is None:raise ValueError('Timestamp must have an explicit time zone')
 return t.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')

def validate_files(value, *, maximum):
 if not isinstance(value,dict)or value.get('private_reference_only')is not True or value.get('external_fetches')!=0:raise ValueError('Complete actual local native file reference required')
 files=value.get('files');paths=set()
 if not isinstance(files,list)or not 1<=len(files)<=maximum:raise ValueError('Bounded complete native file catalogue required')
 for f in files:
  path=f.get('relative_path')if isinstance(f,dict)else None
  if not isinstance(path,str)or Path(path).is_absolute()or '..'in Path(path).parts or path in paths:raise ValueError('Exact unique native source path required')
  paths.add(path);raw=base64.b64decode(f['body_base64'],validate=True)
  if len(raw)!=f['bytes']or not raw or hashlib.sha256(raw).hexdigest()!=f['sha256']:raise ValueError('Every original full native source byte must agree')
 return files

def release_cards(data):
 import yaml
 files=validate_files(data,maximum=512);by={};cards=[]
 for f in files:
  found=re.search(r'(\d{4})[-_]?([01]\d)[-_]?([0-3]\d)',Path(f['relative_path']).stem)
  if not found:raise PendingCapability('Actual native release-file date association unavailable')
  date='-'.join(found.groups());datetime.fromisoformat(date);by[f['relative_path']]=date
 latest=max(by.values())
 from lab_generate_skill.gitlab_release_cards import card_fields
 for f in files:
  if by[f['relative_path']]==latest:
   cards.extend(card_fields(yaml.safe_load(base64.b64decode(f['body_base64']).decode())))
 if not cards or len({c['title']for c in cards})!=len(cards)or any(not c['title'].strip()or not c['description'].strip()for c in cards):raise PendingCapability('Unique complete latest local release cards unavailable')
 return latest,cards

def validate_reference(ref,params):
 """Recompute the private oracle from the complete original local records."""
 if not isinstance(ref,dict)or ref.get('kind')!=params['operation']:raise ValueError('Exact independently read native operation required')
 kind=params['operation']
 if kind=='last_closed':
  rows=ref['closed_rows'];dates=ref['closure_rows']
  if ref['project']['path']!=params['project']or any(r.get('state_id')!=2 or type(r.get('id'))is not int or type(r.get('iid'))is not int or r['id']<=0 or r['iid']<=0 for r in rows):raise ValueError('Exact closed native project rows required; merged is distinct')
  if len({r['id']for r in rows})!=len(rows)or len({r['iid']for r in rows})!=len(rows)or len(dates)!=len(rows)or{r['id']for r in dates}!={r['id']for r in rows}:raise ValueError('Every closed native row needs its independent closure association')
  ids={r['id']:r['iid']for r in rows}
  for d in dates:
   if d['iid']!=ids[d['id']]or d['closed_at']!=timestamp(d['closed_at']):raise ValueError('Exact native closure identity/timestamp differs')
   original=d['native_closed_at']
   if isinstance(original,str)and datetime.fromisoformat(original.replace('Z','+00:00')).tzinfo is None:
    if ref.get('native_timezone')!=[{'database_time_zone':'UTC'}]:raise ValueError('Timezone-less native DB date lacks actual UTC authority')
    original+='+00:00'
   if timestamp(original)!=d['closed_at']:raise ValueError('Original native timestamp bytes/normalization differ')
  latest=max((d['closed_at']for d in dates),default=None)
  answer={'closed_at':latest,'merge_requests':sorted(d['iid']for d in dates if d['closed_at']==latest)}
  if ref['answer']!=answer:raise ValueError('Native latest-closure oracle differs from complete rows')
 elif kind=='literal_projects':
  rows=ref['source_rows'];seen=set();ids=set()
  for r in rows:
   if r['id']in ids or r['path']in seen or r['archived']is not False or r['id']not in ref['access']['project_ids']or not all(isinstance(r[k],str)for k in('path','display_name','description_text')):raise ValueError('Complete accessible unique native directory rows required')
   ids.add(r['id']);seen.add(r['path'])
  expected={'projects':[{'path':p}for p in sorted(r['path']for r in rows if params['term'].casefold()in(r['display_name']+' '+r['description_text']).casefold())]}
  if ref['answer']!=expected:raise ValueError('Complete native literal-description query differs')
 elif kind=='switch_account':
  if any(type(ref.get(k))is not int or ref[k]<=0 for k in('initial_id','target_id'))or ref['initial_id']==ref['target_id']or ref.get('active')is not True or ref.get('ordinary')is not True or ref.get('password_verified')is not True or ref.get('target_username')!=params['target_username']or ref.get('password_or_hash_in_reference')is not False or not re.fullmatch('[0-9a-f]{64}',ref['native_source_sha256'].get('app/models/user.rb','')):raise ValueError('Actual independently qualified distinct active account required')
 elif kind=='whats_new':
  latest,cards=release_cards(ref['native_data'])
  if ref['cards']!=cards or ref['latest_local_release_date']!=latest or ref.get('external_latest_not_claimed')is not True:raise ValueError('Native release-body oracle differs from full shipped source bytes')
 else:
  validate_files(ref['native_views'],maximum=32)
  if ref['required_operations']!=list(OPERATIONS)or ref.get('does_not_create_a_project')is not True:raise ValueError('Explicit description-only native process contract required')
 return True
