"""Actor-visible instance-local inbox for genuine native signup messages.

This reads mail created by the native Rails mailer; it never creates accounts,
tokens or links, follows confirmation URLs, or deletes evidence. A private
website owns each server and outbox. Reset must stop this server and restore
its declared account/token/mail baseline before exposing a new browser.
"""
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import hashlib
import html
import stat
import threading
from urllib.parse import urlsplit

from .map_account_mail import confirmation_from_message

MAX_MESSAGE_BYTES=1024*1024
MAX_MESSAGES=128


def inbox_document(outbox,*,recipient,display_name,origin):
    root=Path(outbox)
    if root.is_symlink() or not root.is_dir():raise ValueError('Private native mail directory required')
    paths=sorted(root.glob('message-*'))
    if len(paths)>MAX_MESSAGES:raise ValueError('Native inbox exceeds bounded message count')
    articles=[];receipts=[]
    for path in paths:
        attrs=path.lstat()
        if not stat.S_ISREG(attrs.st_mode) or attrs.st_size>MAX_MESSAGE_BYTES:
            raise ValueError('Bounded regular native message required')
        payload=path.read_bytes()
        if len(payload)>MAX_MESSAGE_BYTES:raise ValueError('Native message grew beyond limit')
        try:
            match=confirmation_from_message(payload,recipient=recipient,display_name=display_name,origin=origin)
        except ValueError:
            # Mail for another account never enters this task's browser.
            continue
        message=BytesParser(policy=policy.default).parsebytes(payload)
        plain=message.get_body(preferencelist=('plain',))
        text=plain.get_content() if plain is not None else ''
        article='<article><h2>'+html.escape(str(message.get('Subject','Message')))+' </h2>'
        if text:article+='<pre>'+html.escape(text)+'</pre>'
        article+='<p><a href="'+html.escape(match['url'],quote=True)+'">Open account confirmation message link</a></p></article>'
        articles.append(article)
        receipts.append(dict(file=path.name,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest()))
    document='<!doctype html><html lang="en"><meta charset="utf-8"><title>Local account inbox</title><main><h1>Inbox for '+html.escape(recipient)+'</h1>'
    document+=''.join(articles) if articles else '<p>No account confirmation messages yet.</p>'
    document+='</main></html>'
    return document.encode(),receipts


class LocalAccountInbox:
    def __init__(self,outbox,*,recipient,display_name,origin):
        u=urlsplit(origin)
        if (u.scheme not in ('http','https')or u.hostname not in ('127.0.0.1','localhost','::1')
                or u.username or u.password or u.path or u.query or u.fragment):
            raise ValueError('Owned local native website origin required')
        if not recipient or not display_name:raise ValueError('Declared local account required')
        self.outbox=Path(outbox);self.account=dict(recipient=recipient,display_name=display_name,origin=origin)
        inbox_document(self.outbox,**self.account)
        self.closed=False;self.requests=0;self.served_messages={};self.lock=threading.Lock()
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path!='/inbox':
                    self.send_response(404);self.end_headers();return
                try:
                    body,receipts=inbox_document(owner.outbox,**owner.account)
                    with owner.lock:
                        owner.requests+=1
                        owner.served_messages.update({r['sha256']:r for r in receipts})
                    self.send_response(200)
                    self.send_header('Content-Type','text/html; charset=utf-8')
                    self.send_header('Cache-Control','no-store')
                    self.send_header('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'")
                    self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
                except Exception:
                    body=b'Native local inbox unavailable; no confirmation has been performed.'
                    self.send_response(503);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/inbox'
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.05},daemon=True)
        self.thread.start()

    def snapshot(self):
        with self.lock:
            return dict(version='native-map-local-inbox-v1',requests=self.requests,
                messages=list(self.served_messages.values()),closed=self.closed,
                auto_confirmations=0,external_delivery=False)

    def close(self):
        if not self.closed:
            self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
            if self.thread.is_alive():raise RuntimeError('Owned inbox did not stop')
            self.closed=True
        return self.snapshot()
