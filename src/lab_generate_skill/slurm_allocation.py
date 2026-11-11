"""Read actual single-node resources; requested CPUs/task can differ on GPU nodes."""
from decimal import Decimal
import os
import re
import subprocess


def allocation_from_record(record, job_id, *, minimum_cpus, minimum_memory_mib):
    fields=dict(re.findall(r'(\w+)=([^\s]+)',record))
    identity=fields.get('JobId')
    if '_' in job_id:
        parent,task=job_id.split('_',1)
        matched=fields.get('ArrayJobId')==parent and fields.get('ArrayTaskId')==task
    else:matched=identity==job_id
    if not matched or fields.get('JobState')!='RUNNING' or fields.get('NumNodes')!='1':
        raise ValueError('Current running single-node allocation required')
    tres=dict(x.split('=',1)for x in fields.get('AllocTRES','').split(',')if '='in x)
    memory=re.fullmatch(r'(\d+(?:\.\d+)?)([KMGT])',tres.get('mem',''))
    if memory is None:raise ValueError('Actual Slurm memory allocation missing')
    mib=Decimal(memory[1])*{'K':Decimal(1)/1024,'M':1,'G':1024,'T':1024**2}[memory[2]]
    cpus=int(tres.get('cpu','0'))
    if cpus<int(minimum_cpus) or mib<Decimal(minimum_memory_mib):
        raise ValueError('Insufficient actual Slurm CPU or memory allocation')
    return dict(job_id=identity,allocation_query=job_id,cpus=cpus,memory_mib=float(mib),
                node=fields.get('NodeList'),source='scontrol_AllocTRES')


def require_allocation(*,minimum_cpus=8,minimum_memory_mib=60000):
    job=os.environ.get('SLURM_JOB_ID','')
    if not re.fullmatch(r'\d+',job):raise ValueError('Slurm job required')
    parent=os.environ.get('SLURM_ARRAY_JOB_ID');task=os.environ.get('SLURM_ARRAY_TASK_ID')
    if parent is not None or task is not None:
        if not parent or not task or not parent.isdigit()or not task.isdigit():
            raise ValueError('Complete Slurm array identity required')
        job=parent+'_'+task
    result=subprocess.run(['scontrol','show','job',job,'-o'],check=True,
                          capture_output=True,text=True,timeout=15)
    return allocation_from_record(result.stdout,job,minimum_cpus=minimum_cpus,
                                  minimum_memory_mib=minimum_memory_mib)
