"""Saved product-layout controls. Candidate only; caller owns fresh factory/reset/archive."""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
import json,subprocess,time
SOURCE='c8de5316f4877a385aa2'
START='/admin/catalog/product/new/set/4/type/simple/'
KEY='product_design_native'
MATERIAL={'name':'Training Design Product','sku':'TRAINING-DESIGN-PRODUCT','price':'10.00','store_id':1}

def capture(site,project,root,read_base):
    state=read_base();local=Path(site.temp.name)/'webarena-admin';helper=Path(project)/'cluster/admin-product-design-state.php'
    command=['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd','--pwd','/','--bind',str(local)+':/state','--bind',str(local/'app')+':/var/www/magento2','--bind',str(helper)+':/design-state.php:ro',str(Path(root)/'containers/webarena/shopping-admin.sif'),'php','/design-state.php']
    result=subprocess.run(command,capture_output=True,text=True,timeout=45)
    if result.returncode:raise RuntimeError('native_product_design_capture_failed')
    native=json.loads(result.stdout)
    if set(native)!={'entities','websites','attributes','values'}or any(not isinstance(x,list)for x in native.values()):raise ValueError('incomplete_product_design_evidence')
    if KEY in state:raise ValueError('native_design_key_collision')
    state[KEY]=native;return state

def split(state):
    if not isinstance(state,dict)or KEY not in state:raise ValueError('missing_native_design_state')
    native=state[KEY]
    if set(native)!={'entities','websites','attributes','values'}or any(not isinstance(x,list)for x in native.values()):raise ValueError('incomplete_native_design_state')
    layout=[r for r in native['attributes']if r['attribute_code']=='page_layout']
    if len(layout)!=1 or layout[0]['backend_type']!='varchar':raise ValueError('unexpected_native_page_layout_schema')
    return {k:v for k,v in state.items()if k!=KEY},native

def evaluate(before,after):
    try:
        from lab_generate_skill.admin_creation_guard import creation_checks
        initial,bn=split(before);final,an=split(after);checks=creation_checks(initial,final,MATERIAL)
        if not checks.get('one_new_target'):
            checks['unrelated_design_state_unchanged']=bn==an
        else:
            target=next(r for r in final['records']['product']if r['sku']==MATERIAL['sku']);pid=str(target['entity_id']);entity=[r for r in an['entities']if str(r['entity_id'])==pid]
            layout=[r for r in an['values']if str(r['entity_id'])==pid and r['attribute_code']=='page_layout']
            checks['saved_one_column_default_scope']=len(layout)==1 and str(layout[0]['store_id'])=='0'and layout[0]['backend_type']=='varchar'and layout[0]['value']=='1column'
            checks['saved_simple_product_attribute_set']=len(entity)==1 and entity[0]['type_id']=='simple'and str(entity[0]['attribute_set_id'])=='4'and entity[0]['sku']==MATERIAL['sku']
            restored=deepcopy(an);restored['entities']=[r for r in an['entities']if str(r['entity_id'])!=pid];restored['values']=[r for r in an['values']if str(r['entity_id'])!=pid];restored['websites']=[r for r in an['websites']if str(r['product_id'])!=pid];checks['unrelated_design_state_unchanged']=restored==bn
        return {'execution_status':'completed','evaluation_status':'success'if all(checks.values())else'failure','checks':checks,'error':None,'task_reward':None,'training_admitted':False}
    except (ValueError,KeyError,TypeError,StopIteration)as exc:return {'execution_status':'completed','evaluation_status':'unknown','checks':{'native_design_evidence':{'error':type(exc).__name__+': '+str(exc)}},'error':str(exc),'task_reward':None,'training_admitted':False}

