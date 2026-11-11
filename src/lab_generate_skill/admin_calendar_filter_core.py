"""Candidate full-date semantics; requires complete one-page native results, fails unknown otherwise.
Install beside the unchanged date_range_controls.py in scripts/admin18-followup/.
Native positive execution and public derived-contract review remain mandatory.
"""
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import json,re,importlib.util
from copy import deepcopy
SOURCE='7dfd7947cbf21b1561b6'
REFERENCE=date(2023,1,1)

def expected_orders(state,reference=REFERENCE):
    zone=state['display_timezone']
    if not isinstance(zone,str)or not zone:raise ValueError('native_display_timezone_missing')
    tz=ZoneInfo(zone);end=reference.replace(day=1);start=(end-timedelta(days=1)).replace(day=1)
    lo=datetime.combine(start,datetime.min.time(),tz).astimezone(timezone.utc);hi=datetime.combine(end,datetime.min.time(),tz).astimezone(timezone.utc)
    rows=state['records']['order'];ids=[str(x['entity_id'])for x in rows]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate_native_order_identity')
    selected={}
    for row in rows:
        timestamp=datetime.strptime(row['created_at'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        if lo<=timestamp<hi:selected[str(row['entity_id'])]=row
    return selected,{'timezone':zone,'utc_start_inclusive':lo.isoformat(),'utc_end_exclusive':hi.isoformat(),'local_month_start':start.isoformat(),'local_next_month_start':end.isoformat()}

def judge(before,after,grid_checks,grid,provider_items,visible_rows,reference=REFERENCE):
    try:
        expected,bounds=expected_orders(before,reference)
        if before['records']!=after['records']or before['display_timezone']!=after['display_timezone']:raise ValueError('native_read_only_guard_changed')
        if not grid or grid.get('probe_error')or not isinstance(grid.get('provider'),dict):raise ValueError('grid_probe_unavailable')
        provider=grid['provider'];total=provider['total_records']
        if type(total)is not int or total<0 or not isinstance(provider_items,list):raise ValueError('invalid_provider_capture')
        ids=[str(x['entity_id'])for x in provider_items]
        if len(ids)!=len(set(ids))or ids!=provider['row_ids']:raise ValueError('provider_capture_disagrees')
        if total!=len(ids):raise ValueError('full_result_set_not_captured_pagination_required')
        native={str(x['entity_id']):x for x in before['records']['order']};tz=ZoneInfo(bounds['timezone'])
        displayed={}
        if not ids and not expected:raise ValueError('empty_month_requires_separate_native_timezone_display_control')
        for item in provider_items:
            sid=str(item['entity_id'])
            if sid not in native:raise ValueError('provider_native_identity_disagreement')
            # Magento Date::prepareDataSource converts UTC database values to
            # the configured display zone before serializing provider rows.
            # Compare forward UTC -> local (unambiguous across DST folds).
            local=datetime.strptime(native[sid]['created_at'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).astimezone(tz).replace(tzinfo=None)
            if item['created_at']!=local.strftime('%Y-%m-%d %H:%M:%S'):raise ValueError('provider_native_timestamp_disagreement')
            matches=[text for text in visible_rows if re.search(r'(?<!\d)'+re.escape(native[sid]['increment_id'])+r'(?!\d)',text)]
            if len(matches)!=1:raise ValueError('visible_order_identity_not_unique')
            text=' '.join(matches[0].split());match=re.search(r'([A-Z][a-z]{2} \d{1,2}, \d{4}),? (\d{1,2}:\d{2}:\d{2} [AP]M)',text)
            if not match:raise ValueError('visible_order_datetime_unavailable')
            visible=datetime.strptime(match.group(1)+' '+match.group(2),'%b %d, %Y %I:%M:%S %p')
            if visible!=local:raise ValueError('native_display_timezone_not_confirmed')
            displayed[sid]=visible.isoformat()
        required={'required_grid_request_completed','requested_grid_parameters_submitted','requested_grid_parameters_current','grid_response_applied'}
        if set(grid_checks)!=required or any(type(v)is not bool for v in grid_checks.values()):raise ValueError('grid_operation_checks_unavailable')
        checks={**grid_checks,'complete_calendar_month_order_set':set(ids)==set(expected),'native_order_records_unchanged':True,'display_timestamps_match_native_timezone':True}
        return {'execution_status':'completed','evaluation_status':'success'if all(checks.values())else'failure','checks':checks,'bounds':bounds,'expected_ids':sorted(expected),'actual_ids':ids,'displayed':displayed,'error':None,'task_reward':None,'training_admitted':False}
    except (ValueError,TypeError,KeyError)as exc:
        return {'execution_status':'completed','evaluation_status':'unknown','checks':{'full_date_evidence':{'error':type(exc).__name__+': '+str(exc)}},'error':str(exc),'task_reward':None,'training_admitted':False}

