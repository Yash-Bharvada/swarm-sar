"""Reject incomplete comparisons; report predeclared engineering gates."""
import argparse,json
from pathlib import Path
from frozen_development_benchmark import load_protocol,cases,case_key,sha,ROOT


def assess(report,candidate,config,lock):
    if report.get('protocol_sha256')!=lock['protocol_sha256'] or not report.get('complete'):raise ValueError('Incomplete or wrong protocol')
    stage=report['stage'];expected={case_key(c) for c in cases(config,stage)}
    indexed={}
    for row in report['rows']:
        key=(row['mode'],case_key(row))
        if key in indexed:raise ValueError('Duplicate case')
        if not 0<=row['found']<=row['total'] or row['total']<=0:raise ValueError('Invalid survivor counts')
        indexed[key]=row
    for mode in ['ppo','expert',candidate]:
        if {k for m,k in indexed if m==mode}!=expected:raise ValueError('Missing/extra cases: '+mode)
    strata=[]
    for size in config['sizes']:
        for layout in config['layouts']:
            values={}
            for mode in ['ppo','expert',candidate]:
                rr=[indexed[(mode,case_key(c))] for c in cases(config,stage) if c['size']==size and c['layout']==layout]
                values[mode]=sum(r['found'] for r in rr)/sum(r['total'] for r in rr)
            strata.append(dict(size=size,layout=layout,recall=values,delta=values[candidate]-values['ppo']))
    for key in expected:
        if len({indexed[(m,key)]['initial_signature'] for m in ['ppo','expert',candidate]})!=1:raise ValueError('Unpaired initial state')
    large=sum(s['delta'] for s in strata if s['size']>32)/sum(s['size']>32 for s in strata)
    small=sum(s['delta'] for s in strata if s['size']==32)/sum(s['size']==32 for s in strata)
    gates=config['gates'];passed=large>=gates['large_macro_recall_gain_min'] and small>=gates['small_macro_recall_delta_min'] and all(s['delta']>=gates['each_stratum_recall_delta_min'] for s in strata)
    return dict(stage=stage,candidate=candidate,engineering_gates_passed=passed,large_macro_recall_delta=large,small_macro_recall_delta=small,strata=strata,
        limits='Engineering gate on few development seeds; not statistical significance, deployment approval or final validation.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('results',type=Path);p.add_argument('--candidate',required=True,choices=['square5','visible5','visible24']);p.add_argument('--nominate',type=Path)
    a=p.parse_args();config,lock=load_protocol();report=json.loads(a.results.read_text());assessment=assess(report,a.candidate,config,lock)
    if a.nominate:
        if report['stage']!='discovery' or not assessment['engineering_gates_passed']:raise ValueError('Only a passing complete discovery comparison may nominate')
        nomination=dict(mode=a.candidate,protocol_sha256=lock['protocol_sha256'],actor_hashes=report['actor_hashes'],confirmation_consumed=False,
            discovery_results_sha256=sha(a.results),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'simulation/scripts/visibility_frontiers.py',ROOT/'simulation/scripts/frontier_utility.py']})
        with a.nominate.open('x') as f:json.dump(nomination,f,indent=2)
    print(json.dumps(assessment,indent=2))

if __name__=='__main__':main()
