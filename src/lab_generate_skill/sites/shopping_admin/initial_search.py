"""Hold the original navigation search lifecycle before remote preparation.

Only the already owned local service is addressed. No snapshot, task evidence,
recovery, external state or permission is created here.
"""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_commands import container
from .service_contract import AdminServiceSpec
from .search_http_program import SEARCH_HTTP_PHP

INITIAL_SEARCH_HOLD_PHP = (
    r"""
$stage='input';
try {
 if(count($argv)!==3||!ctype_digit($argv[1])||(int)$argv[1]<1024||(int)$argv[1]>65535||!is_numeric($argv[2])||!is_finite((float)$argv[2])||(float)$argv[2]<=0||(float)$argv[2]>86400)throw new RuntimeException('Invalid original search port/budget');
 $port=(int)$argv[1];$until=hrtime(true)/1e9+(float)$argv[2];
"""
    + SEARCH_HTTP_PHP
    + r"""
 function pause_ready(){global $until;$remaining=$until-hrtime(true)/1e9;if($remaining<=0)throw new RuntimeException('Initial search deadline expired');usleep((int)(min(0.1,$remaining)*1e6));}
 $stage='readiness';
 do {
  try {$before=request('GET','/_ilm/status');break;}
  catch(RuntimeException $e){if($e->getMessage()!=='Search HTTP failed'&&strpos($e->getMessage(),'Search HTTP status 503: ')!==0)throw $e;pause_ready();}
 }while(true);
 if(!in_array($before['operation_mode']??null,['RUNNING','STOPPING','STOPPED'],true))throw new RuntimeException('Invalid original ILM mode');
 $identity=request('GET','/');
 if(($identity['version']['number']??null)!=='7.17.0'||!is_string($identity['cluster_uuid']??null)||!preg_match('/^[A-Za-z0-9_-]{1,128}$/D',$identity['cluster_uuid']))throw new RuntimeException('Unexpected original search identity/version');
 $stage='stop_ilm';
 if((request('POST','/_ilm/stop')['acknowledged']??null)!==true)throw new RuntimeException('Initial ILM stop unconfirmed');
 $stage='confirm_stopped';
 do {
  $mode=request('GET','/_ilm/status')['operation_mode']??null;
  if($mode==='STOPPED')break;
  if($mode!=='STOPPING')throw new RuntimeException('Initial ILM stop changed mode');
  pause_ready();
 }while(true);
 $final=request('GET','/');
 if(($final['cluster_uuid']??null)!==$identity['cluster_uuid']||($final['version']['number']??null)!==$identity['version']['number'])throw new RuntimeException('Original search changed during startup hold');
 echo 'search-lifecycle-stopped';
}catch(Throwable $e){fwrite(STDERR,json_encode(['stage'=>$stage,'error'=>get_class($e),'message'=>$e->getMessage()],JSON_UNESCAPED_SLASHES).PHP_EOL);exit(2);}
"""
)


def hold_initial_search(
    spec: AdminServiceSpec, commands: NativeCommands, control: OperationControl
) -> None:
    spec = AdminServiceSpec.model_validate(spec)
    remaining = control.checkpoint()
    result = commands.run(
        container(spec)
        + (
            "php",
            "-r",
            INITIAL_SEARCH_HOLD_PHP,
            str(spec.ports.search),
            str(remaining),
        ),
        control,
    )
    if result != b"search-lifecycle-stopped":
        raise ValueError("Initial search lifecycle stop was not confirmed")
    control.checkpoint()
