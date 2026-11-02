"""Preflight JSON structure before allocating a full portable-backup object graph."""
import json
MAX_DEPTH=64
MAX_CONTAINERS=250000
MAX_STRINGS=2000000
MAX_PRIMITIVES=1000000

def loads(raw,*,reject_duplicates=False):
    depth=containers=strings=primitives=0
    quoted=escaped=atom=False
    for value in raw:
        if quoted:
            if escaped:escaped=False
            elif value==92:escaped=True
            elif value==34:quoted=False
            continue
        if value==34:
            quoted=True;atom=False;strings+=1
            if strings>MAX_STRINGS:raise ValueError('Backup JSON has too many string values')
        elif value in (123,91):
            depth+=1;containers+=1;atom=False
            if depth>MAX_DEPTH or containers>MAX_CONTAINERS:raise ValueError('Backup JSON structure exceeds its safe limit')
        elif value in (125,93):
            depth-=1;atom=False
            if depth<0:raise ValueError('Invalid backup JSON structure')
        elif value in (32,9,10,13,44,58):atom=False
        elif not atom:
            atom=True;primitives+=1
            if primitives>MAX_PRIMITIVES:raise ValueError('Backup JSON has too many scalar values')
    if quoted or depth:raise ValueError('Incomplete backup JSON')
    def invalid(_):raise ValueError('Invalid JSON numeric value')
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise ValueError('Backup JSON contains duplicate object members')
            result[key]=value
        return result
    return json.loads(raw,parse_constant=invalid,**({'object_pairs_hook':pairs} if reject_duplicates else {}))
