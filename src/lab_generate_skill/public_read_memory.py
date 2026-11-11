"""Bounded, task-independent memory of record text actually issued to an actor.

A reader supplies public candidates; acknowledgement occurs only after a real
request, against its final AX text. No navigation, private reference, expected
count, task filtering or model inference is performed here.
"""
import copy,json,re
from urllib.parse import urlsplit

VERSION='public-issued-read-memory-v1'
MARKER='Native public record: '
MEMORY_MARKER='Read-only public observation memory: '
FIELDS={'kind','record_id','url','label','timestamp','displayed_time'}


def norm(value):return ' '.join(value.split())


def metadata_line(row):
    return MARKER+json.dumps({k:v for k,v in row.items()if k!='label'},ensure_ascii=False,sort_keys=True)


def validate(row,origin):
    if not isinstance(row,dict)or set(row)!=FIELDS or not isinstance(row['kind'],str)or not re.fullmatch('[a-z][a-z0-9_]{0,49}',row['kind'])or not(type(row['record_id'])is int and row['record_id']>0 or isinstance(row['record_id'],str)and 0<len(row['record_id'])<=128) or any(not isinstance(row[k],str)for k in('url','label','timestamp','displayed_time'))or not row['label'].strip():raise ValueError('Exact safe public record shape required')
    u=urlsplit(row['url']);o=urlsplit(origin)
    if(u.scheme,u.netloc)!=(o.scheme,o.netloc)or u.username or u.password or u.query or u.fragment or not u.path.startswith('/'):raise ValueError('Public record must use this local site without credentials/query secrets')


def current_observation_bids(observation):
    """Only current AX node entries authorize element operations.

    Previously read public text/record IDs are data, even if a body contains
    bracketed numbers or a previous page's rendered node text. The explicit
    memory block follows the current AX and is never part of the action scope.
    """
    ax=observation.get('axtree_txt','')
    if not isinstance(ax,str):return set()
    current=ax.rsplit('\n\n'+MEMORY_MARKER,1)[0]
    if observation.get('observation_mode')=='full' and observation.get('observation_policy')=='full-lossless-rows-if-fits-v2':
        from .lossless_ax_rows import expand
        current=expand(current)
    return set(re.findall(r'(?m)^[ \t]*\[([^\]\s]+)\][ \t]+\S',current))


class PublicReadMemory:
    def __init__(self,origin,*,max_records=128,max_characters=24000):
        if type(max_records)is not int or max_records<=0 or type(max_characters)is not int or max_characters<=0:raise ValueError('Positive explicit whole-record memory bounds required')
        self.origin=origin;self.max_records=max_records;self.max_characters=max_characters;self.records={};self.omitted=set();self.conflicts=set();self.last_request_memory_omitted=False
    def acknowledge(self,actual_ax,candidates,*,expected_memory_text=None):
        if not isinstance(actual_ax,str)or not isinstance(candidates,list):raise ValueError('Actual issued AX and public candidates required')
        text=norm(actual_ax)
        if expected_memory_text is not None:
            if not isinstance(expected_memory_text,str):raise ValueError('Prepared public memory render required')
            self.last_request_memory_omitted=bool(expected_memory_text and expected_memory_text.strip()not in actual_ax)
        for row in candidates:
            validate(row,self.origin)
            # Metadata alone does not prove the corresponding record body/title
            # was provided. Both must occur in the final request after budgeting.
            if metadata_line(row)not in actual_ax or norm(row['label'])not in text:continue
            key=(row['kind'],row['record_id'],row['url']);old=self.records.get(key)
            if old==row:continue
            if old is not None:self.conflicts.add(key)
            proposed=dict(self.records);proposed[key]=copy.deepcopy(row)
            size=len(json.dumps(list(proposed.values()),ensure_ascii=False,sort_keys=True))
            if len(proposed)>self.max_records or size>self.max_characters:self.omitted.add(key);continue
            self.records=proposed;self.omitted.discard(key)
        return self.snapshot()
    def snapshot(self):
        return {'version':VERSION,'records':copy.deepcopy(list(self.records.values())),
          'capacity':{'records':self.max_records,'characters':self.max_characters},
          'capture_limited':bool(self.omitted),'omitted_whole_records':len(self.omitted),
          'observed_record_changed':bool(self.conflicts),'last_request_memory_omitted':self.last_request_memory_omitted,'complete_task_result_asserted':False}
    def render(self):return render_snapshot(self.snapshot())


def render_snapshot(state):
    if not state['records']and not state['capture_limited']:return ''
    return '\n\n'+MEMORY_MARKER+json.dumps(state,ensure_ascii=False,sort_keys=True)+'\nThis is previously received public text, not a claim that the task or collection is complete.'


class IssuedPublicReadActor:
    """Transparent inference wrapper: one call, then final-request acknowledgement."""
    def __init__(self,delegate,acknowledge):self.delegate=delegate;self.acknowledge=acknowledge
    def __getattr__(self,name):return getattr(self.delegate,name)
    def generate(self,messages,*,seed):
        result=self.delegate.generate(messages,seed=seed)
        sent=getattr(self.delegate,'last_request_messages',None)
        # Production MeasuredActor always exposes the final sent request. An
        # unknown backend must not silently acknowledge its prebudget input.
        if isinstance(sent,list)and sent:
            try:payload=json.loads(next(m['content']for m in reversed(sent)if m.get('role')=='user'))
            except(ValueError,TypeError,KeyError,StopIteration):payload=None
            if isinstance(payload,dict)and isinstance(payload.get('observation'),str):self.acknowledge(payload['observation'])
        return result


class PublicReadProtocol:
    """Refresh confirmed public memory before the unchanged token-budget policy.

    This also handles parse retries on the same page: no browser step is needed
    to retain text the previous generation actually received.
    """
    def __init__(self,delegate,refresh):self.delegate=delegate;self.refresh=refresh
    def __getattr__(self,name):return getattr(self.delegate,name)
    def prepare_observation(self,goal,obs,history,**kwargs):
        return self.delegate.prepare_observation(goal,self.refresh(obs),history,**kwargs)
