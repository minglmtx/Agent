"""Optional two-client complete native bbox read, bounded by one original deadline.

Only actual unchanged50K-cap400 responses split rectangles. Main-thread callbacks
preserve full/partial bytes; no Playwright object enters a worker thread. A full
union is returned only after every leaf passed existing strict native XML checks.
"""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import heapq,time
import xml.etree.ElementTree as ET
from .map_native_bbox_batch import (Response,NativeBatchError,exact_bounds,split_bounds,union_xml,
    CAP_ERROR,NATIVE_NODE_CAP,MAX_REQUESTS,MAX_DEPTH,digest,artifact,xml_objects)
from .map_native_bbox_http_client import NativeMapHttpClient,NativeHttpReadError

VERSION='map-native-two-independent-http-clients-v1'


def fetch_complete_two(original,clients,*,deadline,initial_response=None,preserve=None,max_requests=MAX_REQUESTS):
    if (not isinstance(clients,(tuple,list))or len(clients)!=2 or clients[0] is clients[1]
            or any(not isinstance(c,NativeMapHttpClient)for c in clients)or clients[0].origin!=clients[1].origin):
        raise ValueError('Two distinct exact-origin independent native HTTP clients required')
    if type(max_requests)is not int or not 1<=max_requests<=MAX_REQUESTS:raise ValueError('Unchanged bounded native request budget required')
    bounds=exact_bounds(original);ledger=[];leaves=[];pending=[((),bounds,0)];running={};available=[0,1]
    executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='native-map-independent-read')
    failed=None
    def saved(item,payload=None):
        if preserve is not None:preserve(item['request_index'],item,payload)
    def entry(path,cell,depth):
        item={'request_index':len(ledger),'split_path':list(path),'parent_split_path':list(path[:-1])if path else None,
            'bounds':list(cell),'http_status':None,'depth':depth,'status':'started','seconds':None,'body_complete':False}
        ledger.append(item);saved(item);return item
    def consume(item,response,started):
        if not isinstance(response,Response)or type(response.status)is not int or not isinstance(response.body,bytes)or not isinstance(response.content_type,str):
            item.update(status='invalid_response_schema',seconds=time.monotonic()-started);saved(item)
            raise NativeBatchError('Actual native child response schema unavailable',ledger)
        item.update(status='response_received',http_status=response.status,content_type=response.content_type,
            bytes=len(response.body),sha256=digest(response.body),seconds=time.monotonic()-started,body_complete=True)
        saved(item,response.body)
        if time.monotonic()>deadline:raise NativeBatchError('Native full-bbox absolute deadline exhausted after response',ledger)
        if response.status==400 and CAP_ERROR.fullmatch(response.body):
            item['native_node_cap']=NATIVE_NODE_CAP;saved(item,response.body)
            if item['depth']>=MAX_DEPTH:raise NativeBatchError('Native full-bbox subdivision depth exhausted',ledger)
            for number,child in enumerate(split_bounds(item['bounds'])):
                heapq.heappush(pending,(tuple(item['split_path'])+(number,),child,item['depth']+1))
            return
        if response.status!=200 or response.content_type.split(';',1)[0].strip().lower()not in ('application/xml','text/xml'):
            raise NativeBatchError('Native bbox child is not actual HTTP200 XML; non-cap error preserved',ledger)
        try:
            parsed,_=xml_objects(response.body)
            if parsed['bounds']!=artifact.native_xml_bbox(item['bounds']):raise ValueError('Native child bbox changed')
        except (ValueError,ET.ParseError,TypeError,KeyError)as error:
            raise NativeBatchError('Actual native child XML invalid',ledger)from error
        leaves.append((item['bounds'],response.body))
    def timed_fetch(client,cell,absolute_deadline):
        began=time.monotonic()
        try:response=client.fetch(cell,absolute_deadline)
        except NativeHttpReadError as error:
            error.record['http_seconds']=time.monotonic()-began;raise
        return response,time.monotonic()-began
    def future_record(future,item,started,*,allow_split):
        try:
            response,http_seconds=future.result();item['http_seconds']=http_seconds
        except Exception as error:
            item.update(status='transport_failed',failure_type=type(error).__name__,seconds=time.monotonic()-started)
            payload=None
            if isinstance(error,NativeHttpReadError):item.update(error.record);payload=error.partial
            saved(item,payload)
            raise NativeBatchError('Actual independent native child transport failed before complete response',ledger)from error
        if allow_split:consume(item,response,started)
        else:
            item.update(status='response_retained_after_batch_failure',http_status=response.status,content_type=response.content_type,
                bytes=len(response.body),sha256=digest(response.body),seconds=time.monotonic()-started,body_complete=True)
            saved(item,response.body)
    try:
        if initial_response is not None:
            path,cell,depth=heapq.heappop(pending);item=entry(path,cell,depth);consume(item,initial_response,time.monotonic())
        while pending or running:
            if deadline<=time.monotonic():raise NativeBatchError('Native full-bbox original absolute deadline exhausted',ledger)
            while pending and available:
                if len(ledger)>=max_requests:raise NativeBatchError('Native full-bbox unchanged request budget exhausted',ledger)
                path,cell,depth=heapq.heappop(pending);item=entry(path,cell,depth);slot=available.pop(0);started=time.monotonic()
                future=executor.submit(timed_fetch,clients[slot],cell,deadline);running[future]=(slot,item,started)
            done,_=wait(running,timeout=max(0,deadline-time.monotonic()),return_when=FIRST_COMPLETED)
            if not done:raise NativeBatchError('Native full-bbox original absolute deadline exhausted',ledger)
            for future in sorted(done,key=lambda f:tuple(running[f][1]['split_path'])):
                slot,item,started=running.pop(future);available.append(slot);future_record(future,item,started,allow_split=True)
        if time.monotonic()>=deadline:raise NativeBatchError('Native full-bbox original deadline exhausted before union',ledger)
        payload,summary=union_xml(bounds,leaves)
        if time.monotonic()>deadline:raise NativeBatchError('Native full-bbox original deadline exhausted during union',ledger)
        summary.update(requests=sorted(ledger,key=lambda i:tuple(i['split_path'])),native_parent_http_status=ledger[0]['http_status'],
            no_private_oracle_used_to_construct_union=True,each_child_uses_original_native_endpoint=True,
            transport_version=VERSION,maximum_independent_http_clients=2,playwright_thread_shared=False,
            original_absolute_deadline_renewed=False,complete_full_union_required=True)
        return payload,summary
    except Exception as error:
        failed=error
        for client in clients:client.cancel()
        # Socket shutdown interrupts actual blocking header/body reads. Retain all
        # completed responses and any partial body, but never construct a union.
        for future,(slot,item,started)in list(running.items()):
            try:
                future.result(timeout=2)
            except Exception:pass
            if future.done():
                try:future_record(future,item,started,allow_split=False)
                except Exception:pass
            else:
                item.update(status='native_client_cleanup_unknown',body_complete=False);saved(item)
        raise NativeBatchError(str(error),sorted(ledger,key=lambda i:tuple(i['split_path'])))from error
    finally:
        if failed is not None:executor.shutdown(wait=False,cancel_futures=True)
        else:executor.shutdown(wait=True)
