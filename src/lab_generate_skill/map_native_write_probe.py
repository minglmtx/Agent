"""Private bounded native API probe, not an actor tool or task evaluator."""
import base64
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
import xml.etree.ElementTree as ET
from .io_utils import atomic_write_json


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalWriteProbe:
    def __init__(self, origin, account, directory):
        p = urlsplit(origin)
        if (p.scheme != 'http' or p.hostname != '127.0.0.1' or p.port is None
                or p.username or p.password or p.path or p.query or p.fragment):
            raise ValueError('Explicit leased loopback website origin required')
        self.origin, self.account = origin, account
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=False)
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.calls = []

    def request(self, method, path, body=None, *, authenticated=True):
        p = urlsplit(path)
        if (method not in ('GET', 'PUT') or p.scheme or p.netloc or p.query or p.fragment
                or not path.startswith('/api/0.6/') or '\\' in path):
            raise ValueError('Bounded native capability endpoint required')
        if len(self.calls) >= 24:
            raise ValueError('Native request budget exhausted; no automatic retry')
        headers = {'Content-Type': 'text/xml', 'Accept': 'text/xml'}
        if authenticated:
            identity = self.account['display_name'] + ':' + self.account['password']
            headers['Authorization'] = 'Basic ' + base64.b64encode(identity.encode()).decode()
        data = None if body is None else body.encode()
        request = Request(self.origin + path, data=data, method=method, headers=headers)
        try:
            response = self.opener.open(request, timeout=25)
        except HTTPError as error:
            response = error
        with response:
            status = response.code
            raw = response.read(2*1024*1024+1)
        if len(raw) > 2*1024*1024:
            raise ValueError('Native response exceeds small-object capability budget')
        row = dict(method=method, path=path, authenticated=authenticated, status=status,
                   request_body=body, response_body=raw.decode('utf-8'),
                   response_sha256=hashlib.sha256(raw).hexdigest())
        self.calls.append(row)
        atomic_write_json(self.directory/'requests.json', {'calls':self.calls, 'paid_api_calls':0})
        return row


def osm_node(*, changeset, lat, lon, tags, node_id=None, version=None):
    attributes = dict(changeset=str(changeset), lat=str(lat), lon=str(lon))
    if node_id is not None:attributes['id'] = str(node_id)
    if version is not None:attributes['version'] = str(version)
    root=ET.Element('osm',version='0.6');node=ET.SubElement(root,'node',attributes)
    for key,value in sorted(tags.items()):ET.SubElement(node,'tag',k=key,v=value)
    return ET.tostring(root,encoding='unicode')


def read_node(receipt):
    if receipt['status'] != 200:raise ValueError('Native node GET did not succeed')
    text=receipt['response_body']
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('Unexpected native XML declarations')
    root=ET.fromstring(text); nodes=root.findall('node')
    if root.tag!='osm' or len(nodes)!=1:raise ValueError('One actual native node required')
    node=nodes[0];tags={t.attrib['k']:t.attrib['v'] for t in node.findall('tag')}
    if len(tags)!=len(node.findall('tag')):raise ValueError('Duplicate node tag keys')
    attrs=node.attrib
    return dict(id=int(attrs['id']),version=int(attrs['version']),changeset=int(attrs['changeset']),
                lat=attrs['lat'],lon=attrs['lon'],visible=attrs.get('visible')=='true',tags=tags)
