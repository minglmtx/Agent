"""Actual original pinned-image search snapshot/restore, no formal writer authority."""

import json
import os
from pathlib import Path
from typing import Any, Literal
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from lab_generate_skill.sites.shopping_admin.service_contract import AdminServiceSpec
from lab_generate_skill.sites.shopping_admin.service_commands import container
from lab_generate_skill.sites.shopping_admin.search import AdminSearch
from lab_generate_skill.sites.shopping_admin.search_contract import AdminSearchSnapshot
from lab_generate_skill.sites.shopping_admin.search_program import SEARCH_SNAPSHOT_PHP
from test_admin_services_native import run_admin_services_probe
from test_slurm_commands import guard

PROBE = r"""
try {
 $port=(int)$argv[1];$phase=$argv[2];
 function call($method,$path,$body=null){global $port;
 $o=['method'=>$method,'timeout'=>20,'ignore_errors'=>true,'follow_location'=>0,'header'=>"Content-Type: application/json\r\n"];
 if($body!==null)$o['content']=json_encode($body,JSON_THROW_ON_ERROR);
 $raw=file_get_contents('http://127.0.0.1:'.$port.$path,false,stream_context_create(['http'=>$o]));
 if($raw===false||!preg_match('/^HTTP\/[0-9.]+ ([0-9]{3})/',$http_response_header[0]??'',$m))throw new RuntimeException('Probe HTTP failed');
 return [(int)$m[1],json_decode($raw,true,64,JSON_THROW_ON_ERROR)];}
 if($phase==='seed'){
  [$status,$r]=call('PUT','/lab-recovery-probe',['settings'=>['number_of_shards'=>1,'number_of_replicas'=>0,'refresh_interval'=>'2s'],'mappings'=>['properties'=>['value'=>['type'=>'keyword']]],'aliases'=>['lab-recovery-alias'=>new stdClass()]]);if($status!==200||($r['acknowledged']??null)!==true)throw new RuntimeException('Seed index failed');
  [$status,$r]=call('PUT','/lab-recovery-probe/_doc/one?refresh=wait_for',['value'=>'original']);if($status!==201)throw new RuntimeException('Seed document failed');
 }elseif($phase==='mutate'){
  [$status,$r]=call('PUT','/lab-recovery-probe/_doc/one?refresh=wait_for',['value'=>'changed']);if($status!==200)throw new RuntimeException('Mutation failed');
  [$status,$r]=call('PUT','/lab-recovery-extra',['settings'=>['number_of_shards'=>1,'number_of_replicas'=>0]]);if($status!==200)throw new RuntimeException('New index failed');
  [$status,$r]=call('POST','/_aliases',['actions'=>[['remove'=>['index'=>'lab-recovery-probe','alias'=>'lab-recovery-alias']]]]);if($status!==200)throw new RuntimeException('Alias mutation failed');
  [$status,$r]=call('PUT','/lab-recovery-probe/_settings',['index'=>['refresh_interval'=>'3s']]);if($status!==200)throw new RuntimeException('Setting mutation failed');
 }elseif($phase==='verify'){
  [$status,$r]=call('GET','/lab-recovery-probe/_doc/one');if($status!==200||($r['_source']['value']??null)!=='original')throw new RuntimeException('Original document not restored');
  [$status,$r]=call('GET','/lab-recovery-extra');if($status!==404)throw new RuntimeException('Extra index remains');
  [$status,$r]=call('GET','/_alias/lab-recovery-alias');if($status!==200||!isset($r['lab-recovery-probe']['aliases']['lab-recovery-alias']))throw new RuntimeException('Original alias not restored');
  [$status,$r]=call('GET','/lab-recovery-probe/_settings');if($status!==200||($r['lab-recovery-probe']['settings']['index']['refresh_interval']??null)!=='2s')throw new RuntimeException('Original setting not restored');
  [$status,$r]=call('GET','/lab-recovery-probe/_mapping');if($status!==200||($r['lab-recovery-probe']['mappings']['properties']['value']['type']??null)!=='keyword')throw new RuntimeException('Original mapping not retained');
 }else{throw new RuntimeException('Unknown probe');}
 echo 'ok';
}catch(Throwable $e){fwrite(STDERR,get_class($e).': '.$e->getMessage().PHP_EOL);exit(2);}
"""


class Authority:
    def __init__(self, service: AdminServiceSpec) -> None:
        self.service = service

    def verify(
        self,
        service: AdminServiceSpec,
        phase: Literal["save", "verify", "preflight", "restore"],
        snapshot: AdminSearchSnapshot | None,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert service == self.service
        assert (snapshot is None) == (phase == "save")
        # Sole engineering fixture client, no browser/Actor; not production authority.


def probe(service: AdminServiceSpec, commands: NativeCommands) -> dict[str, Any]:
    def call(phase: str) -> None:
        assert (
            commands.run(
                container(service)
                + ("php", "-r", PROBE, str(service.ports.search), phase),
                guard(30),
            )
            == b"ok"
        )

    call("seed")
    worker = AdminSearch(service, commands, Authority(service))
    saved = worker.save(guard(60))
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    (output / "admin-search-original-snapshot.json").write_text(
        saved.model_dump_json(indent=2) + "\n"
    )
    assert "lab-recovery-probe" in saved.indices
    assert (
        saved.data_streams
    ), "Pinned historical seed must exercise data stream restoration"
    worker.verify(saved, guard(20))
    call("mutate")
    restored = worker.restore(saved, guard(60))
    (output / "admin-search-restored.json").write_text(
        restored.model_dump_json(indent=2) + "\n"
    )
    call("verify")
    worker.verify(saved, guard(20))
    return dict(
        snapshot=saved.model_dump(mode="json"),
        restored=restored.model_dump(mode="json"),
        original_document_restored=True,
        new_index_removed=True,
        original_alias_and_settings_restored=True,
        original_mapping_retained=True,
        complete_site_reset=False,
        formal_writer_authority=False,
    )


def test_actual_search_snapshot_restore_original_document_and_index_set() -> None:
    run_admin_services_probe(probe, programs=(SEARCH_SNAPSHOT_PHP, PROBE))
