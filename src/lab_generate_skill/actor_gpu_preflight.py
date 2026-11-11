"""Small actual CUDA kernel check before website/model initialization."""
import time


def run_kernels(torch, index):
    device='cuda:'+str(index)
    # Allocation alone does not prove the installed wheel can execute kernels
    # on this architecture. Check model arithmetic and token-selection kernels.
    x=torch.ones((16,16),device=device,dtype=torch.bfloat16)
    scores=(x@x).float().softmax(dim=-1)
    token=scores.argmax(dim=-1)
    torch.cuda.synchronize(index)
    if not torch.isfinite(scores).all().item() or token.numel()!=16:
        raise RuntimeError('CUDA smoke result invalid')


def inspect(torch):
    started=time.monotonic()
    report=dict(version='actor-cuda-kernel-preflight-v1',passed=False,devices=[],
                torch_version=str(torch.__version__),compiled_cuda=str(torch.version.cuda),
                compiled_architectures=list(torch.cuda.get_arch_list()),
                model_loaded=False,website_started=False,actor_attempts=0,api_calls=0)
    try:
        if not torch.cuda.is_available() or torch.cuda.device_count()<1:
            raise RuntimeError('No visible CUDA device for local actor')
        for index in range(torch.cuda.device_count()):
            row=dict(index=index,name=torch.cuda.get_device_name(index),
                     capability=list(torch.cuda.get_device_capability(index)),kernel_passed=False)
            report['devices'].append(row)
            run_kernels(torch,index)
            row['kernel_passed']=True
        report['passed']=True
    except Exception as exc:
        report['error']=dict(type=type(exc).__name__,message=str(exc)[:1000])
    report['seconds']=time.monotonic()-started
    return report
