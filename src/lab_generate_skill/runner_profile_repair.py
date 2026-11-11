"""Exact ordinary-runner profile forwarding repair; no actor/evaluator edits."""
import ast
from copy import deepcopy


def verify_runner_patch(original,repaired):
    old=ast.parse(original);new=ast.parse(repaired);expected=deepcopy(old)
    main=next(n for n in expected.body if isinstance(n,ast.FunctionDef)and n.name=='main')
    imports=[n for n in main.body if isinstance(n,ast.ImportFrom)and n.module=='lab_generate_skill.website_batch_profile']
    if len(imports)!=1 or [n.name for n in imports[0].names]!=['profile']:
        raise ValueError('Original ordinary profile import changed')
    imports[0].names.append(ast.alias(name='optional_worker_options'))
    first=next(i for i,n in enumerate(main.body)if isinstance(n,ast.If)and
               ast.unparse(n.test)=="optional_profile.get('map_account') is not None")
    for offset,key in enumerate(('map_account','map_existing_account')):
        wanted=ast.parse(f"if optional_profile.get('{key}') is not None:\n    site_options['{key}']=optional_profile['{key}']").body[0]
        if ast.dump(main.body[first+offset],include_attributes=False)!=ast.dump(wanted,include_attributes=False):
            raise ValueError('Original account forwarding changed')
    main.body[first:first+2]=ast.parse('site_options.update(optional_worker_options(optional_profile))').body
    candidates=[n for n in ast.walk(main)if isinstance(n,ast.IfExp)and
        ast.unparse(n.test)=="name == 'map' and (optional_profile.get('map_account') or optional_profile.get('map_existing_account'))"]
    if len(candidates)!=1:raise ValueError('Original instance selection changed')
    candidates[0].test=ast.parse("name=='map' and any(optional_profile.get(k)for k in ('map_account','map_existing_account','map_short_routes','map_raster_export'))",mode='eval').body
    if ast.dump(expected,include_attributes=False)!=ast.dump(new,include_attributes=False):
        raise ValueError('Profile repair changed unrelated runner behavior')
    return True
