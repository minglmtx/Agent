"""Background native bbox reads behind a real loopback HTTP response.

The Playwright routing callback only registers a request and continues it. All
native HTTP, splitting, parsing and complete-union work happens in the HTTP
handler. No Playwright object or callback enters that worker. The first native
400 and all child bytes stay preserved; exact scope and the 50K cap are unchanged.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import threading
import time
import uuid
from .map_native_bbox_batch import CAP_ERROR, Response, digest
from .map_native_bbox_http_client import NativeMapHttpClient, NativeHttpReadError
from .map_native_bbox_parallel import fetch_complete_two
from .io_utils import atomic_write_json


class BackgroundNativeMap:
    def __init__(self, owner):
        self.owner = owner
        self.prefix = '/native-map-pending/' + uuid.uuid4().hex + '/'
        self.jobs = {}
        self.active = set()
        self.lock = threading.RLock()
        self.closed = False
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self): outer._get(self)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.server.block_on_close = False
        self.thread = threading.Thread(target=self.server.serve_forever,
            kwargs={'poll_interval': .05}, name='native-map-background-http', daemon=True)
        self.thread.start()

    def register(self, number, record, directory, deadline):
        with self.lock:
            if self.closed: raise ValueError('Native transport is closed')
            target = self.prefix + str(number) + '.osm'
            job = {'record': record, 'directory': Path(directory), 'deadline': deadline,
                'clients': [], 'connection': None, 'thread': None, 'started': False}
            self.jobs[target] = job
            return 'http://127.0.0.1:' + str(self.server.server_port) + target

    def _update(self, job, **values):
        with self.owner.lock:
            job['record'].update(values)
            self.owner._save()

    def _get(self, request):
        origin = request.headers.get('Origin')
        if origin not in (None, self.owner.origin): request.send_error(403); return
        with self.lock:
            job = self.jobs.get(request.path)
            if job is None: request.send_error(404); return
            if self.closed or job['started']: request.send_error(410); return
            job['started'] = True
            job['connection'] = request.connection
            job['thread'] = threading.current_thread()
            self.active.add(job['thread'])
        record = job['record']; directory = job['directory']; began = time.monotonic()
        original = None
        try:
            with self.lock:
                client = NativeMapHttpClient(self.owner.origin)
                job['clients'].append(client)
                if self.closed: client.cancel()
            try: original = client.fetch(record['requested_bbox_strings'], job['deadline'])
            finally: client.cancel()
            (directory / 'native-original-response.bin').write_bytes(original.body)
            self._update(job, native_original_http_status=original.status,
                native_original_body_sha256=digest(original.body),
                native_original_content_type=original.content_type,
                native_original_body_bytes=len(original.body),
                native_original_body_file=directory.name + '/native-original-response.bin')
            body = original.body; status = original.status; content_type = original.content_type
            if original.status == 400 and CAP_ERROR.fullmatch(original.body):
                def preserve(index, meta, payload):
                    filename = 'child-' + str(index) + '.osm' if payload is not None else None
                    if payload is not None: (directory / filename).write_bytes(payload)
                    atomic_write_json(directory / ('child-' + str(index) + '.json'),
                        dict(meta, payload_file=filename))
                clients = [NativeMapHttpClient(self.owner.origin), NativeMapHttpClient(self.owner.origin)]
                with self.lock:
                    job['clients'].extend(clients)
                    if self.closed:
                        for client in clients: client.cancel()
                try:
                    body, summary = fetch_complete_two(record['requested_bbox_strings'], clients,
                        deadline=job['deadline'], initial_response=original, preserve=preserve)
                finally:
                    for client in clients: client.cancel()
                path = directory / 'complete-adapted-map.osm'; path.write_bytes(body)
                status = 200; content_type = 'application/xml; charset=utf-8'
                self._update(job, status='native_children_complete_adapted_envelope',
                    batch=summary, envelope=directory.name + '/complete-adapted-map.osm',
                    native_original_http_status=400, adapted_browser_response_http_status=200,
                    adapted_response_is_native_original_http200=False)
            else:
                self._update(job, status='native_response_unchanged')
            self._send(request, job, status, content_type, body)
        except Exception as error:
            details = {'status': 'batch_transport_unknown', 'failure_type': type(error).__name__,
                'ledger': getattr(error, 'ledger', None),
                'failure_category': getattr(error, 'reason_code', 'transport_or_browser_error')}
            if isinstance(error, NativeHttpReadError):
                (directory / 'native-original-partial.bin').write_bytes(error.partial)
                details['native_original_partial_read'] = error.record
            self._update(job, **details)
            # Genuine original errors remain genuine errors. Never return a
            # partial union or fabricated success after a timeout/cancellation.
            if original is not None:
                try: self._send(request, job, original.status, original.content_type, original.body)
                except Exception as failure:
                    self._update(job, native_original_delivery_failure_type=type(failure).__name__)
            else:
                try: request.send_error(502, 'Native map transport unavailable')
                except Exception: pass
        finally:
            self._update(job, seconds=time.monotonic() - began, background_handler_finished=True)
            with self.lock:
                self.active.discard(job['thread']); job['connection'] = None

    def _send(self, request, job, status, content_type, body):
        # Preserve full bytes. This avoids both the DevTools base64 pipe and
        # waiting for the complete native fetch inside the Playwright callback.
        deadline = time.monotonic() + 90
        event = {'status': 'starting', 'bytes': 0}
        self._update(job, delivery={'mode': 'private_background_loopback_http',
            'uncompressed_bytes': len(body), 'uncompressed_sha256': digest(body),
            'content_type': content_type, 'requests': [event], 'closed': False,
            'payload_reduced': False, 'native_original_http200_claim':
                job['record'].get('native_original_http_status') == 200})
        request.connection.settimeout(10)
        request.send_response(status)
        request.send_header('Content-Type', content_type)
        request.send_header('Content-Length', str(len(body)))
        request.send_header('Cache-Control', 'no-store')
        request.send_header('Access-Control-Allow-Origin', self.owner.origin)
        request.end_headers()
        started = time.monotonic()
        try:
            for offset in range(0, len(body), 1024 * 1024):
                if self.closed or time.monotonic() >= deadline:
                    raise TimeoutError('Bounded native delivery expired or closed')
                block = body[offset:offset + 1024 * 1024]
                request.wfile.write(block)
                with self.owner.lock: event['bytes'] += len(block)
            with self.owner.lock: event['status'] = 'complete'
        except Exception as error:
            with self.owner.lock: event.update(status='delivery_failed', error_type=type(error).__name__)
            raise
        finally:
            with self.owner.lock: event['seconds'] = time.monotonic() - started
            self._update(job, delivery=job['record']['delivery'])

    def close(self):
        with self.lock:
            if self.closed: return
            self.closed = True
            jobs = list(self.jobs.values())
        # Stop accepting new requests; active readers are independently owned
        # sockets and cancellation interrupts their complete native reads.
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=1)
        for job in jobs:
            for client in job['clients']: client.cancel()
            connection = job['connection']
            if connection is not None:
                try: connection.shutdown(2)
                except OSError: pass
        deadline = time.monotonic() + 5
        for job in jobs:
            thread = job['thread']
            if thread is not None: thread.join(timeout=max(0, deadline - time.monotonic()))
        with self.lock:
            unfinished = len(self.active)
        with self.owner.lock:
            for job in jobs:
                delivery = job['record'].get('delivery')
                if delivery is not None: delivery['closed'] = True
                if job['started'] is False:
                    job['record'].update(status='batch_transport_unknown',
                        failure_category='browser_never_requested_registered_native_job')
            self.owner._save()
        if unfinished: raise RuntimeError('Native background request teardown is incomplete')
