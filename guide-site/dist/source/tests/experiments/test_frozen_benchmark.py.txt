import sys,copy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'simulation/scripts'))
from frozen_development_benchmark import load_protocol,cases,case_key
from assess_development_benchmark import assess


def fixture():
    config,lock=load_protocol();rows=[]
    for c in cases(config,'discovery'):
        for mode,found in [('ppo',5),('expert',6),('visible5',7 if c['size']>32 else 5)]:
            rows.append(dict(**c,mode=mode,found=found,total=10,initial_signature=case_key(c)))
    return dict(stage='discovery',protocol_sha256=lock['protocol_sha256'],complete=True,rows=rows),config,lock


def test_stages_disjoint_and_outside_sealed_final_split():
    config,_=load_protocol()
    assert set(config['stages']['discovery']).isdisjoint(config['stages']['confirmation'])
    assert len(cases(config,'discovery'))==36
    assert all(10000<=c['seed']<10100 for s in config['stages'] for c in cases(config,s))


def test_incomplete_duplicate_or_unpaired_results_cannot_pass():
    report,config,lock=fixture()
    assert assess(report,'visible5',config,lock)['engineering_gates_passed']
    for kind in ['incomplete','missing','duplicate','unpaired']:
        r=copy.deepcopy(report)
        if kind=='incomplete':r['complete']=False
        if kind=='missing':r['rows'].pop()
        if kind=='duplicate':r['rows'].append(r['rows'][0])
        if kind=='unpaired':r['rows'][0]['initial_signature']='other'
        with pytest.raises(ValueError):assess(r,'visible5',config,lock)


def test_average_gain_cannot_hide_a_small_map_or_layout_regression():
    r,c,l=fixture()
    for row in r['rows']:
        if row['mode']=='visible5' and row['size']==32:row['found']=4
    assert not assess(r,'visible5',c,l)['engineering_gates_passed']
    r,c,l=fixture()
    for row in r['rows']:
        if row['mode']=='visible5' and row['size']==56 and row['layout']=='maze':row['found']=4
    assert not assess(r,'visible5',c,l)['engineering_gates_passed']
