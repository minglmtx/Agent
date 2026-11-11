"""Complete live users schema, with explicit PostgreSQL dropped-slot evidence.

Only catalog metadata is collected. Numbering gaps alone are never permission
to skip a column; all physical slots and every non-dropped column must agree.
"""
import json,os
from pathlib import Path
from .heldout_preferences_binding import require

VERSION='heldout-preferences-users-schema-v1'
COLUMNS_SQL="SELECT column_name,data_type,ordinal_position FROM information_schema.columns WHERE table_schema='public' AND table_name='users' ORDER BY ordinal_position"
CATALOG_SQL="SELECT n.nspname AS table_schema,c.relname AS table_name,c.oid::text AS relation_oid,c.relkind,c.relnatts,a.attnum,a.attname,a.attisdropped,a.atttypid::bigint AS type_oid,pg_catalog.format_type(a.atttypid,NULL) AS data_type FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid WHERE n.nspname='public' AND c.relname='users' AND a.attnum>0 ORDER BY a.attnum"


def validate_users_schema(columns,catalog,field):
    require(isinstance(columns,list)and columns and isinstance(catalog,list)and catalog,
            'Both actual users schema catalogs required')
    require(all(isinstance(r,dict)and set(r)=={'column_name','data_type','ordinal_position'}
                and isinstance(r['column_name'],str)and r['column_name']
                and isinstance(r['data_type'],str)and r['data_type']
                and type(r['ordinal_position'])is int and r['ordinal_position']>0 for r in columns),
            'Complete typed live column rows required')
    names=[r['column_name']for r in columns];ordinals=[r['ordinal_position']for r in columns]
    require(len(names)==len(set(names))and len(ordinals)==len(set(ordinals))
            and ordinals==sorted(ordinals)and {'id','username','last_seen',field}<=set(names),
            'Every required live users column in unique catalog order is required')
    keys={'table_schema','table_name','relation_oid','relkind','relnatts','attnum','attname','attisdropped','type_oid','data_type'}
    for row in catalog:
        require(isinstance(row,dict)and set(row)==keys and row['table_schema']=='public'
                and row['table_name']=='users'and row['relkind']=='r'
                and isinstance(row['relation_oid'],str)and row['relation_oid'].isdigit()
                and int(row['relation_oid'])>0 and type(row['relnatts'])is int and 0<row['relnatts']<=1600
                and type(row['attnum'])is int and row['attnum']>0
                and isinstance(row['attname'],str)and row['attname']
                and type(row['attisdropped'])is bool and type(row['type_oid'])is int
                and ((row['attisdropped']and row['type_oid']==0)or(not row['attisdropped']and row['type_oid']>0))
                and isinstance(row['data_type'],str), 'Actual physical users attribute metadata incomplete')
    header={(r['relation_oid'],r['relnatts'])for r in catalog}
    require(len(header)==1 and [r['attnum']for r in catalog]==list(range(1,catalog[0]['relnatts']+1)),
            'Every physical user column slot, including dropped slots, required')
    live=[dict(column_name=r['attname'],data_type=r['data_type'],ordinal_position=r['attnum'])
          for r in catalog if not r['attisdropped']]
    require(columns==live,'Live information_schema columns differ from all non-dropped physical attributes')
    return dict(live_columns=len(live),physical_slots=len(catalog),
                explicitly_dropped_slots=[r['attnum']for r in catalog if r['attisdropped']],
                every_live_column_verified=True)


def _save(path,value):
    with Path(path).open('x')as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())


def capture_users_schema(site,output,field):
    from .site_database import select_rows
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    result=dict(version=VERSION,columns_query=COLUMNS_SQL,catalog_query=CATALOG_SQL,
                columns=None,catalog=None,query_error_type=None)
    try:
        result['columns']=select_rows(site,COLUMNS_SQL)
        result['catalog']=select_rows(site,CATALOG_SQL)
    except BaseException as exc:
        result['query_error_type']=type(exc).__name__;raise
    finally:
        # Always persist both raw results (or explicit unavailable fields)
        # before shape checks, preserving an actual rejected schema diagnosis.
        _save(output/'users-schema.json',result)
    checks=validate_users_schema(result['columns'],result['catalog'],field)
    _save(output/'users-schema-review.json',dict(passed=True,checks=checks))
    return result['columns'],result['catalog']
