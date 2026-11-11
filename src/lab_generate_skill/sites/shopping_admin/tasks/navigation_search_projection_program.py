"""Exact held-search cross-instance projection, separate from recovery hash."""

SEARCH_METADATA_NORMALIZATION_PHP = r"""
 function normalized($metadata){$metadata=unserialize(serialize($metadata));unset($metadata->cluster_uuid,$metadata->cluster_uuid_committed,$metadata->cluster_coordination);
  foreach($metadata->indices as $name=>$index){if(!is_object($index->settings->index??null))throw new RuntimeException('Index settings missing');unset($index->settings->index->uuid,$index->settings->index->creation_date,$index->primary_terms,$index->in_sync_allocations);}
  return $metadata;
 }
"""

SEARCH_EQUIVALENCE_PHP = r"""
 function equivalence_metadata($metadata){
  if(($metadata->index_lifecycle->operation_mode??null)!=='STOPPED')throw new RuntimeException('Cross-instance search comparison requires held ILM');
  $metadata=normalized($metadata);
  $repository=$metadata->repositories->lab_admin_recovery??null;
  if(!is_object($repository)||($repository->type??null)!=='fs'||!is_string($repository->uuid??null)||!preg_match('/^[A-Za-z0-9_-]{1,128}$/D',$repository->uuid)||($repository->settings->location??null)!=='/state/elasticsearch/snapshots'||($repository->settings->compress??null)!=='true'||!is_int($repository->generation??null)||$repository->generation<0||!is_int($repository->pending_generation??null)||$repository->pending_generation<$repository->generation)throw new RuntimeException('Original physical search repository required');
  unset($repository->uuid);
  foreach($metadata->indices as $index){
   if(!property_exists($index,'ilm'))continue;
   if(!is_object($index->ilm))throw new RuntimeException('Complete held ILM state required');
   foreach(['phase','action','step']as$key)if(!is_string($index->ilm->$key??null)||$index->ilm->$key==='')throw new RuntimeException('Complete held ILM position required');
   foreach(['action_time','phase_time','step_time']as$key){
    $value=$index->ilm->$key??null;
    if(!is_string($value)||!preg_match('/^[1-9][0-9]{0,14}$/D',$value))throw new RuntimeException('Exact held ILM transition timestamp required');
    unset($index->ilm->$key);
   }
  }
  return $metadata;
 }
"""
