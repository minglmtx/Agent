"""Bind a public array element to its exact Slurm internal allocation ID.

Alex TMPDIR names use the numeric SLURM_JOB_ID. A public array root/index is
not that ID. Never accept a sibling or strip the suffix as an identity guess.
Terminal state is still independently verified by the continuation authority.
"""
from pathlib import Path
import re
import subprocess

def allocation_tmpdir_matches(job_id, directory, *, query=None):
    if not isinstance(job_id,str) or re.fullmatch(r'[1-9][0-9]*(?:_[0-9]+)?',job_id) is None:
        raise ValueError('Exact allocation or array element required')
    leaf=Path(directory).name
    if re.fullmatch(r'[1-9][0-9]*\.alex',leaf) is None:return False
    internal=leaf.removesuffix('.alex')
    if '_' not in job_id:return internal==job_id
    if query is None:
        def query(job):
            return subprocess.check_output(['sacct','-X','-n','-P','-j',job,'--format=JobID,JobIDRaw'],text=True,timeout=20)
    rows=[]
    for line in query(job_id).splitlines():
        fields=line.split('|')
        if len(fields)>=2 and fields[0]==job_id:
            rows.append(fields[1])
    return len(rows)==1 and rows[0]==internal and re.fullmatch(r'[1-9][0-9]*',rows[0]) is not None
