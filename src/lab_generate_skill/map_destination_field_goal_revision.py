"""Explicit same-capability named-field derivatives with unchanged source starts."""
from copy import deepcopy
from .source_revision_binding import binding,require_source_binding
from .map_route_normal_capture import fingerprint
from .map_native_identity_declarations import POLICIES,POLICY_SHA

VERSION='native-named-destination-field-derived-v1'
SUFFIX='--native-destination-training-v1'

# Query-level receipts from the byte-verified original native control packet.
# Unrelated new place policies must not invalidate an unchanged named field.
REVIEWED_POLICY_COMPONENTS = {'dd3ef63993269a16736f7515e3f416e5adc040ec89d6cc5adbb9e13e7c41e6f2': {'Chicago': 'd4315b9ff01f4fd38388355a6746e1e7e017b32cccc29e8110baefa492d7f148', 'Detroit': 'bd2b7c619f95d44cc9585de018a300c300a6fb91921bc400d9cd985f09ab6078', 'Miami': '17098ec5dc0584318738496b630093bde4f530e12aecfd075be6f82bbaefe257', 'Orlando': '65a08d9399e7b06b3d02a1691e927d71229a2799ba0b5e38a48ab07c40cda7d3', 'New York, NY': 'fdf45f5bfd41eb8dc551012917349f3db663c4a3bef0655c4bd85bbec31d308e', 'New York City': 'fdf45f5bfd41eb8dc551012917349f3db663c4a3bef0655c4bd85bbec31d308e', 'Washington, DC': 'f3c7fc7b2bd138621dc0ee4391b12eee3c7fc5fdf742b982ef76db1df9f3fb74', 'Washington DC': 'f3c7fc7b2bd138621dc0ee4391b12eee3c7fc5fdf742b982ef76db1df9f3fb74', 'Rochester': '3ecbde1b4fe76ef6e1a06f079d0864b02f3657d1176b2780809c350272bd0080', 'Syracuse': 'd122c3d0c548048e34c5cb60c8dd3b37c340671b65a607ff90f22809f7e5ba38', 'Buffalo': 'd11d3bc6d9e8ffcbfc06d6c2504afabbdc7892e445aa71cd495e5d6c9a3e5e85', 'Boston': 'c19871a9c34c2dddffe727520789d766fa148ecfdb886ab6d0acf2c0d438281c', 'Los Angeles': '44d4a6772c57544b80725c9347c94215ae2d3ecc5e412eb354df378924ede82b', 'San Diego': '0b1312523e893f420702678b736264ec6c24209b216f8774acf8a8a99846fc58', 'San Francisco': '92ffd7dcbecef9c04c72e3a4c9b9b20fc3f621e9d09f89e66d2c616bad3adc69', 'Oakland': 'e81b7c3431893488815a121478c78b44d1d9f4fc5c9659ea7103ea818d9c6d88', 'Manhattan': '37fbc867251a20ccd9a96d443593d51ff176362e4f65918941c5e72bd36d6444', 'Brooklyn': '73d5c6529f82f817753966ec2e511075b97a216cc212510c2b1f00e9d1b882eb', 'Upper Manhattan': '13c91ff5ae3e9a30f5b425aa28e0af4643c92fdaa6c51a79d5e1489f37614af8', 'Lower Manhattan': '79b0c5d23d6ff6c9b3d5bf59f5ff97f26498c03f24f1b3229e9fc86e19f64e43', 'Central Park': 'bc6c9c5bba87d3bee174630696ad71e7ff534ed2c29a76e002ea9fcd154eb492', 'Times Square': '192c4656f5986c6ddd08e984907f1d0f0a21ff84568f7257fed0dd9ea178a72f', 'Times Square, New York': '192c4656f5986c6ddd08e984907f1d0f0a21ff84568f7257fed0dd9ea178a72f', 'Empire State Building': '48033f3f9e18e247591ef203062e2a2043f97f380e14100390f451487d8ec0e9', 'Brooklyn Bridge': '7c22edad971f826d23669d1d2d9e1317aa7cbe7da5e0d9b9bcbcb57fa708c2f6', 'JFK Airport': '49678a82cc8ef4e41de6fbda9a1f190b555a7201bf5d49b99674ed1c99ec51ff'}}

def same_reviewed_policy(digest, query):
    if digest == POLICY_SHA:
        return True
    expected = REVIEWED_POLICY_COMPONENTS.get(digest, {}).get(query)
    return expected is not None and query in POLICIES and fingerprint(POLICIES[query]) == expected


def public_goal(query,original_goal):
    return ('Set '+query+' as the destination in the native direction-search To field. '
      'This explicit local training derivative preserves the destination-field operation and its complete native named-place existence check. '
      'It replaces the original destination with the publicly named '+query+'. The original goal "'+original_goal+'", all original starts and traces, '
      'and all old scores remain unchanged. It does not claim equivalence to the original destination task. Route completion is not required.')

def validate(c):
    binding(c);revision=c.get('goal_revision',{})
    original=revision.get('original_contract');query=c.get('endpoint_request',{}).get('query')
    if (revision.get('version')!=VERSION or c.get('task_id')!=c['source_task_id']+SUFFIX
        or c.get('task_text_changed')is not True or c.get('is_explicit_derivative')is not True
        or c.get('original_evaluation_equivalence')is not False
        or not isinstance(original,dict)or original.get('task_id')!=c['source_task_id']
        or original.get('source_task_id')!=c['source_task_id'] or original.get('goal')!=c.get('original_goal')
        or original.get('goal_revision')or original.get('training_initialization')
        or original.get('completion_kind')!='native_destination_field'
        or original.get('endpoint_request',{}).get('kind')!='one_native_field'
        or not isinstance(original['endpoint_request'].get('query'),str)
        or c.get('start_revision')or c.get('training_initialization')
        or c.get('initialization_revision')is not None or c.get('task_text_revision')is not None
        or revision.get('original_contract_sha256')!=fingerprint(original)
        or revision.get('original_goal')!=original['goal'] or revision.get('derived_goal')!=c['goal']
        or revision.get('equivalent_to_original_goal')is not False
        or not same_reviewed_policy(revision.get('policy_sha256'),query)
        or query not in POLICIES or query==original['endpoint_request']['query']
        or c['goal']!=public_goal(query,original['goal'])):
        raise ValueError('Complete explicit named-field source revision required')
    expected=deepcopy(original)
    expected.update(task_id=c['source_task_id']+SUFFIX,goal=public_goal(query,original['goal']),
      task_text_changed=True,is_explicit_derivative=True,goal_revision=deepcopy(revision))
    expected['endpoint_request']['query']=query
    if {k:v for k,v in c.items()if k!='admission_result'}!=expected:
        raise ValueError('Named-field derivative must preserve every original condition except its declared destination and goal')
    return {'query':query,'original_query':original['endpoint_request']['query']}

def derive(original,query):
    c=deepcopy(original)
    c.update(task_id=original['source_task_id']+SUFFIX,goal=public_goal(query,original['goal']),
      task_text_changed=True,is_explicit_derivative=True)
    c['endpoint_request']['query']=query
    c['goal_revision']={'version':VERSION,'original_goal':original['goal'],'derived_goal':c['goal'],
      'reason':'Actual complete independently captured native query has no original named destination identity; use a declared genuinely native local destination without changing field capability.',
      'equivalent_to_original_goal':False,'original_contract':deepcopy(original),
      'original_contract_sha256':fingerprint(original),'policy_sha256':POLICY_SHA}
    validate(c);return c

def require_original_binding(c,original,inventory):
    validate(c);return require_source_binding(c,original,inventory,domain='map')
