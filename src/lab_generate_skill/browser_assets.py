"""Declared upload files: bytes remain local; only task-resource metadata reaches actors."""
import ast
import hashlib
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field


class BrowserUploadFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    description: str = Field(default='',max_length=500)


def upload_file_metadata(files):
    result=[];seen=set()
    for asset in files:
        asset=BrowserUploadFile.model_validate(asset)
        path=Path(asset.path)
        if not path.is_absolute():raise ValueError('Task upload paths must be absolute')
        if path.is_symlink() or not path.is_file():raise ValueError('Task upload asset is not a regular file')
        canonical=str(path.resolve())
        if canonical in seen:raise ValueError('Duplicate task upload file')
        seen.add(canonical)
        size=path.stat().st_size
        if size>20_000_000:raise ValueError('Task upload asset exceeds 20 MB')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=asset.sha256:raise ValueError('Task upload asset changed')
        result.append({'path':canonical,'sha256':digest,'bytes':size,'description':asset.description})
    return result


def validate_upload_action(action, files):
    """Reject invented filenames; no browser action or task outcome is synthesized."""
    call=ast.parse(action,mode='eval').body
    if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name) or call.func.id!='upload_file':return
    if len(call.args)>=2:value=ast.literal_eval(call.args[1])
    else:
        argument=next((k.value for k in call.keywords if k.arg=='file'),None)
        if argument is None:raise ValueError('upload_file requires the declared file path or [] to clear selection')
        value=ast.literal_eval(argument)
    paths=[value] if isinstance(value,str) else value
    if not isinstance(paths,list) or any(not isinstance(p,str) or not p.strip() for p in paths):
        raise ValueError('upload_file requires a file path or list of paths')
    allowed={f['path']:f for f in files}
    for name in paths:
        if name not in allowed:raise ValueError('Upload path is not an available task file; use available_files')
        # Repeat integrity check immediately before a requested upload.
        upload_file_metadata([BrowserUploadFile(path=name,sha256=allowed[name]['sha256'])])
