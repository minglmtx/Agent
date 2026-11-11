from pathlib import Path, PurePosixPath
import hashlib,json,tarfile,importlib.util
def require(ok,message):
 if not ok:raise ValueError(message)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as stream:
  for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()
def pin(path):return {'path':str(path),'sha256':sha(path)}
def load(path):return json.loads(Path(path).read_text())
def verified(ref):
 p=Path(ref['path']);require(p.is_file()and not p.is_symlink()and sha(p)==ref['sha256'],'Pinned file differs:'+str(p));return p

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def archive(index_path,archive_path):
 index=load(index_path);require(sha(archive_path)==index['archive_sha256'],'Archive SHA differs');expected=index['members'];raw={}
 with tarfile.open(archive_path,'r:gz')as stream:
  for entry in stream:
   path=PurePosixPath(entry.name);require(not path.is_absolute()and '..'not in path.parts and entry.isfile()and entry.name not in raw and entry.name in expected,'Unexpected archive member')
   data=stream.extractfile(entry).read();row=expected[entry.name];require(len(data)==entry.size==row['bytes']and hashlib.sha256(data).hexdigest()==row['sha256'],'Archive member differs:'+entry.name);raw[entry.name]=data
 require(set(raw)==set(expected),'Incomplete archive');return raw,index

def unpack(index,archive_path,destination):
 raw,manifest=archive(index,archive_path)
 for name,b in raw.items():
  p=Path(destination)/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 return raw,manifest
