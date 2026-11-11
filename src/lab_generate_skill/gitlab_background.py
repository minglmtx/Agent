"""Run one explicitly selected local native queue, never a wildcard worker."""
import json
import time

QUEUE='repository_fork'
PREFIX='resque:gitlab:'
LOCAL_QUEUES=frozenset((QUEUE,'group_import'))


def require_queue(queue):
    if queue not in LOCAL_QUEUES:
        raise ValueError('Only native local fork or file-group-import queues are supported')
    return queue


def command(*,queue=QUEUE):
    require_queue(queue)
    # Direct Sidekiq CLI avoids the cluster wrapper's fixed exporter port.
    # Nonzero worker ID disables the native first-worker health TCP listener.
    return ['bash','/state/service.sh','gitlab-rails','/usr/bin/env',
        'SIDEKIQ_WORKER_ID=1','SIDEKIQ_LOG_ARGUMENTS=false',
        'prometheus_multiproc_dir=/state/sidekiq-metrics',
        '/opt/gitlab/embedded/bin/bundle','exec','sidekiq',
        '-e','production','-c','2','-t','20','-r','/opt/gitlab/embedded/service/gitlab-rails',
        '-q',queue]


def verify_process(info,*,queue=QUEUE):
    require_queue(queue)
    if (not isinstance(info,dict) or info.get('queues')!=[queue]
            or info.get('concurrency')!=2):
        raise ValueError('Native background worker escaped the admitted queue/concurrency scope')


def start(site, *, timeout=120,queue=QUEUE):
    require_queue(queue)
    began=time.monotonic()
    cli=['/opt/gitlab/embedded/bin/redis-cli','--raw','-s','/var/opt/gitlab/redis/redis.socket']
    def redis(*args):
        return site.command(cli+list(args),capture_output=True,text=True,timeout=15).stdout.strip()
    pending=int(redis('LLEN',PREFIX+'queue:'+queue))
    if pending:
        raise ValueError('Pristine snapshot contains pending native work; refusing to execute unrelated jobs')
    known=set(redis('SMEMBERS',PREFIX+'processes').splitlines())
    (site.state/'sidekiq-metrics').mkdir(exist_ok=True)
    label='sidekiq-fork' if queue==QUEUE else 'sidekiq-group-import'
    site.launch(label,command(queue=queue))
    worker=site.processes[-1]
    while time.monotonic()-began < timeout:
        if worker.poll() is not None:raise RuntimeError('Native background worker exited; inspect '+label+' log')
        new=set(redis('SMEMBERS',PREFIX+'processes').splitlines())-known
        if len(new)>1:raise RuntimeError('Unexpected multiple native background workers')
        if new:
            raw=redis('HGET',PREFIX+next(iter(new)),'info')
            if raw:
                info=json.loads(raw);verify_process(info,queue=queue)
                phase='native_fork_worker_ready' if queue==QUEUE else 'native_group_import_worker_ready'
                site.timed(phase,began,queues=[queue],concurrency=2,pristine_pending_jobs=pending)
                return
        time.sleep(1)
    raise TimeoutError('Native fork worker registration exceeded its readiness budget')
