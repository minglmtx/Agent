"""Independent anonymous loopback HTTP clients, never Playwright/thread sharing."""
import http.client
import errno
import select
import socket
import ipaddress
import threading
import time
from urllib.parse import urlsplit
from .map_native_bbox_batch import Response, child_api_path, MAX_NATIVE_CHILD_BYTES, digest

class NativeHttpReadError(IOError):
    def __init__(self,message,record,partial):
        super().__init__(message);self.record=record;self.partial=partial

class NativeMapHttpClient:
    def __init__(self,origin):
        parsed=urlsplit(origin)
        try:address=ipaddress.ip_address(parsed.hostname or '')
        except ValueError:raise ValueError('Exact anonymous native loopback origin required')
        if (parsed.scheme!='http' or not address.is_loopback or parsed.username is not None
                or parsed.password is not None or parsed.path not in ('','/') or parsed.query or parsed.fragment
                or parsed.port is None or not 1<=parsed.port<=65535):
            raise ValueError('Exact anonymous native loopback origin required')
        self.address_version=address.version
        self.origin=origin.rstrip('/');self.host=parsed.hostname;self.port=parsed.port
        self.lock=threading.Lock();self.connection=None;self.socket=None;self.cancelled=threading.Event()

    def cancel(self):
        self.cancelled.set()
        with self.lock:connection=self.connection;sock=self.socket
        if connection is not None:
            if sock is not None:
                try:sock.shutdown(2)
                except OSError:pass
            connection.close()

    def fetch(self,bounds,deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0 or self.cancelled.is_set():raise TimeoutError('Original absolute native deadline exhausted')
        connection=http.client.HTTPConnection(self.host,self.port,timeout=remaining)
        with self.lock:
            if self.connection is not None:raise ValueError('Independent client cannot have concurrent requests')
            self.connection=connection
        chunks=[];record={'http_status':None,'content_type':None,'body_complete':False,'request_path':child_api_path(bounds)}
        try:
            # No cookies, authorization, redirect following, proxy, or expected data.
            # Own the raw socket before connecting, so sibling failure can
            # cancel even a connect stall without sharing a browser transport.
            sock=socket.socket(socket.AF_INET6 if self.address_version==6 else socket.AF_INET,socket.SOCK_STREAM)
            with self.lock:self.socket=sock
            sock.setblocking(False)
            error=sock.connect_ex((self.host,self.port))
            if error not in(0,errno.EISCONN,errno.EINPROGRESS,errno.EWOULDBLOCK,errno.EALREADY):
                raise OSError(error,'Native loopback connect failed')
            while error not in(0,errno.EISCONN):
                remaining=deadline-time.monotonic()
                if remaining<=0 or self.cancelled.is_set():raise TimeoutError('Original native connect deadline exhausted')
                _,ready,failed=select.select([],[sock],[sock],min(.05,remaining))
                if ready or failed:
                    error=sock.getsockopt(socket.SOL_SOCKET,socket.SO_ERROR)
                    if error:raise OSError(error,'Native loopback connect failed')
            if self.cancelled.is_set():raise TimeoutError('Original native HTTP client cancelled')
            sock.setblocking(True);sock.settimeout(max(.001,deadline-time.monotonic()));connection.sock=sock
            connection.request('GET',record['request_path'],headers={'Accept':'application/xml'})
            remaining=deadline-time.monotonic()
            if remaining<=0 or self.cancelled.is_set():raise TimeoutError('Original native deadline exhausted before headers')
            if connection.sock is not None:connection.sock.settimeout(remaining)
            response=connection.getresponse();record.update(http_status=response.status,content_type=response.getheader('Content-Type',''))
            declared=response.getheader('Content-Length')
            if declared is not None and (not declared.isdecimal() or int(declared)>MAX_NATIVE_CHILD_BYTES):
                raise ValueError('Native response exceeds unchanged64MiB inspection budget')
            total=0
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0 or self.cancelled.is_set():raise TimeoutError('Original absolute native response deadline exhausted')
                if connection.sock is not None:connection.sock.settimeout(remaining)
                # read1 permits rechecking the absolute budget between socket reads.
                block=response.read1(1024*1024)
                if not block:break
                total+=len(block);chunks.append(block)
                if total>MAX_NATIVE_CHILD_BYTES:raise ValueError('Native response exceeds unchanged64MiB inspection budget')
            body=b''.join(chunks)
            if declared is not None and len(body)!=int(declared):raise http.client.IncompleteRead(body)
            if self.cancelled.is_set() or time.monotonic()>deadline:raise TimeoutError('Original native deadline exhausted after response')
            return Response(response.status,record['content_type'],body)
        except Exception as error:
            partial=b''.join(chunks);record.update(bytes=len(partial),sha256=digest(partial),failure_type=type(error).__name__)
            raise NativeHttpReadError('Actual independent native HTTP read did not complete',record,partial)from error
        finally:
            connection.close()
            with self.lock:
                if self.socket is not None:self.socket.close()
                self.connection=None;self.socket=None
