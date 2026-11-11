"""Deliver one validated full native MapData envelope over loopback HTTP.

Large XML must not be base64-injected over Chromium's bounded DevTools pipe.
This serves only the caller's pinned immutable file, never a directory/proxy.
The normal page request is continued to this private transport; no actor action,
map geometry, downloaded artifact, native cap, or site document is changed.
"""
import hashlib,os,stat,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

MAX_BODY_BYTES=128*1024*1024
CHUNK_BYTES=1024*1024

class LoopbackMapDelivery:
    def __init__(self,path,expected_sha256,origin,*,seconds=90):
        u=urlsplit(origin)
        if (u.scheme not in ('http','https')or not u.netloc or u.username or u.password
                or u.path not in ('','/')or u.query or u.fragment or not 0<seconds<=300):
            raise ValueError('Exact source origin and bounded delivery lifetime required')
        self.origin=u.scheme+'://'+u.netloc;self.path=Path(path)
        self.fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            st=os.fstat(self.fd)
            if not stat.S_ISREG(st.st_mode)or not 0<st.st_size<=MAX_BODY_BYTES:raise ValueError('Bounded regular XML envelope required')
            self.identity=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns);self.size=st.st_size
            h=hashlib.sha256();offset=0
            while offset<self.size:
                block=os.pread(self.fd,min(CHUNK_BYTES,self.size-offset),offset)
                if not block:raise ValueError('Incomplete native envelope')
                h.update(block);offset+=len(block)
            self.sha256=h.hexdigest()
            if self.sha256!=expected_sha256:raise ValueError('Complete native envelope digest differs')
            self.target='/native-map/'+uuid.uuid4().hex+'.osm';self.deadline=time.monotonic()+seconds
            self.events=[];self.lock=threading.Lock();self.closed=False;owner=self
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):owner._get(self)
            self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            self.server.daemon_threads=True;self.server.block_on_close=False
            self.url=f'http://127.0.0.1:{self.server.server_port}'+self.target
            self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.05},daemon=True)
            self.thread.start()
        except BaseException:
            os.close(self.fd);raise

    def _get(self,request):
        if request.path!=self.target:request.send_error(404);return
        if request.headers.get('Origin') not in (None,self.origin):request.send_error(403);return
        if self.closed or time.monotonic()>=self.deadline:request.send_error(410);return
        st=os.fstat(self.fd)
        if (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)!=self.identity:request.send_error(409);return
        event={'status':'starting','bytes':0};started=time.monotonic()
        with self.lock:self.events.append(event)
        try:
            request.connection.settimeout(min(10,max(.1,self.deadline-time.monotonic())))
            request.send_response(200);request.send_header('Content-Type','application/xml; charset=utf-8')
            request.send_header('Content-Length',str(self.size));request.send_header('Cache-Control','no-store')
            request.send_header('Access-Control-Allow-Origin',self.origin);request.end_headers()
            offset=0
            while offset<self.size:
                if time.monotonic()>=self.deadline:raise TimeoutError('Native delivery expired')
                block=os.pread(self.fd,min(CHUNK_BYTES,self.size-offset),offset)
                if not block:raise ValueError('Native delivery file ended early')
                request.wfile.write(block);offset+=len(block);event['bytes']=offset
            event['status']='complete'
        except Exception as error:event.update(status='delivery_failed',error_type=type(error).__name__)
        finally:event['seconds']=time.monotonic()-started

    def continue_request(self,route):
        # Chromium validates the previous page referrer against the transport
        # URL override. Only this private delivery strips that header; the
        # actor-visible URL and every other request remain unchanged.
        headers={k:v for k,v in route.request.headers.items()if k.lower() not in ('referer','cookie','authorization','proxy-authorization')}
        # Omitting Referer leaves Chromium's cached referrer in place; an
        # explicit empty value clears it for the internal cross-port transfer.
        headers['referer']=''
        route.continue_(url=self.url,headers=headers)

    def receipt(self):
        with self.lock:events=[dict(x)for x in self.events]
        return {'mode':'private_loopback_http','uncompressed_bytes':self.size,'uncompressed_sha256':self.sha256,
                'content_type':'application/xml; charset=utf-8','requests':events,'closed':self.closed,
                'payload_reduced':False,'native_original_http200_claim':False}

    def close(self):
        if self.closed:return
        self.closed=True
        try:self.server.shutdown();self.server.server_close();self.thread.join(timeout=1)
        finally:os.close(self.fd)
