"""Passive save/readback receipts for the ordinary Map Session.record lifecycle."""
from pathlib import Path
from urllib.parse import urlsplit,unquote
import json,re


def classify(path):
    path=unquote(path).rstrip('/')
    if path in ('/traces','/diary'):return dict(kind='saved',family='upload'if path=='/traces'else'diary')
    m=re.fullmatch(r'/user/([^/]+)/(traces|diary)/(\d+)',path)
    if m:return dict(kind='reopened',family='upload'if m[2]=='traces'else'diary',author=m[1],object_id=m[3])
    return None


def write(path,value):
    with Path(path).open('x')as f:json.dump(value,f,indent=2);f.write('\n')


def wrap_session(Base,directory):
    directory=Path(directory)
    class SaveSession(Base):
        def __init__(self,*args,**kwargs):
            self.save_responses=[];self.save_captures=[];self.save_errors=[];self.save_index_written=False
            super().__init__(*args,**kwargs)

        def reset(self,*args,**kwargs):
            result=super().reset(*args,**kwargs);self.save_origin=urlsplit(self.env.page.url)
            self.env.page.on('requestfinished',self.finished);self.env.page.on('requestfailed',self.failed)
            return result

        def finished(self,request):
            u=urlsplit(request.url);kind=classify(u.path)
            if kind is None or (kind['kind']=='saved'and request.method!='POST'):return
            try:
                if (u.scheme,u.netloc)!=(self.save_origin.scheme,self.save_origin.netloc):raise ValueError('Foreign native save/readback response')
                response=request.response()
                if response is None:raise ValueError('Finished request lacks native response')
                self.save_responses.append(dict(kind,sequence=len(self.save_responses),next_observation_step=self.index,url=request.url,status=response.status,method=request.method,resource_type=request.resource_type,native_response_completed=True,completion_basis='native-requestfinished-event'))
            except Exception as exc:self.save_errors.append(type(exc).__name__+': '+str(exc))

        def failed(self,request):
            row=classify(urlsplit(request.url).path)
            if row and (row['kind']=='reopened'or request.method=='POST'):self.save_errors.append('Native save/readback request failed: '+str(request.failure))

        def record(self,observation,action=None):
            step=self.index;super().record(observation,action);kind=classify(urlsplit(observation.get('url','')).path)
            if kind is None or kind['kind']!='reopened':return
            try:
                from lab_generate_skill.browser_http_status import is_error_document
                page=self.env.page;responses=[r for r in self.save_responses if r['kind']=='reopened'and r['url']==page.url and r['method']=='GET'and r['resource_type']=='document']
                response=responses[-1]if responses else None;status=response['status']if response else None;title=page.title()
                health=dict(url=page.url,title=title,http_status=status,login_page=urlsplit(page.url).path=='/login',error_page=is_error_document(page.url,status,title))
                row=dict(kind,step=step,url=page.url,page=health,response=response,capture_error=None)
            except Exception as exc:
                error=type(exc).__name__+': '+str(exc);self.save_errors.append(error);row=dict(step=step,capture_error=error)
            self.save_captures.append(row);write(directory/f'save-page-{step:03d}.json',row)

        def close(self):
            try:return super().close()
            finally:
                if not self.save_index_written:
                    write(directory/'save-index.json',dict(responses=self.save_responses,captures=self.save_captures,errors=self.save_errors));self.save_index_written=True
    return SaveSession


def witnessed(kind,c,bodies,index):
    if kind not in ('upload','diary'):raise ValueError('Unsupported native Map save family')
    if index['errors']or any(r['status']>=400 for r in index['responses']):raise ValueError('Native request or capture failure')
    captures={r['step']:r for r in index['captures']}
    if len(captures)!=len(index['captures']):raise ValueError('Duplicate public-readback capture')
    events=[];used=set()
    for step,body in enumerate(bodies):
        row=captures.get(step)
        if row is None:continue
        if row.get('capture_error')or row['page']['login_page']or row['page']['error_page']:raise ValueError('Native reopened document unhealthy')
        if row['family']!=kind:continue
        if body['goal']!=c['goal']or body['url']!=row['url']:raise ValueError('Actual public input differs from native capture')
        response=row['response']
        if response is None:continue
        if response not in index['responses']or response['method']!='GET'or response['resource_type']!='document':raise ValueError('Unbound native document GET')
        if response['object_id']!=row['object_id']or response['author']!=row['author']or response['url']!=row['url']:raise ValueError('Readback native identity differs')
        saves=[r for r in index['responses']if r['kind']=='saved'and r['family']==kind and r['method']=='POST'and r['sequence']<response['sequence']]
        if not saves:continue
        saved=saves[-1]
        if saved['sequence']not in used:events.append(dict(saved,view_index=saved['next_observation_step']));used.add(saved['sequence'])
        events.append(dict(response,view_index=step,public_observation=body['observation']))
    return dict(capture_complete=True,events=events)
