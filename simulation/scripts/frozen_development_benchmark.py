"""Frozen benchmark validation and explicit opt-in CPU execution. No training."""
import argparse,hashlib,json,subprocess,time,gzip
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
CONFIG=ROOT/'docs/benchmarks/large_map_development_v1.json'
LOCK=CONFIG.with_suffix('.lock.json')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def load_protocol():
    config=json.loads(CONFIG.read_text());lock=json.loads(LOCK.read_text())
    if sha(CONFIG)!=lock['protocol_sha256']:raise ValueError('Protocol changed: create a new version, do not silently reuse the lock')
    for relative,digest in lock['source_sha256'].items():
        if sha(ROOT/relative)!=digest:raise ValueError('Locked source changed: '+relative)
    from swarm_sar.validation.seeds import load_seed_splits
    development=set(load_seed_splits()['development']);allocated=[]
    for seeds in config['stages'].values():
        if len(seeds)!=len(set(seeds)) or not set(seeds)<=development:raise ValueError('Invalid development seeds')
        allocated.extend(seeds)
    if len(set(allocated))!=len(allocated):raise ValueError('Stages overlap')
    return config,lock

def cases(config,stage):
    return [dict(size=size,layout=layout,seed=seed) for size in config['sizes'] for layout in config['layouts'] for seed in config['stages'][stage]]

def case_key(c):return f"{c['size']}_{c['layout']}_{c['seed']}"

def env_config(config,c):
    return dict(curriculum=False,domain_randomization=False,world_sizes=[c['size']],max_steps=config['max_steps'],
        network_enabled=config['network_enabled'],fixed_team_profile=config['team'],final_team_profiles=[config['team']],
        world_overrides={**config['world_overrides'],'layout':c['layout'],
            **({'num_rooms':config['room_count_by_size'][str(c['size'])]} if c['layout']=='rooms' else {})})

def signature(env):
    return hashlib.sha256(env.core.grid.tobytes()+json.dumps(env.core.victims,sort_keys=True).encode()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['discovery','confirmation'],default='discovery')
    p.add_argument('--execute',action='store_true');p.add_argument('--smoke-worlds',action='store_true')
    p.add_argument('--output',type=Path);p.add_argument('--candidate-lock',type=Path)
    p.add_argument('--candidate',choices=['square5','visible5','visible24'])
    a=p.parse_args();config,lock=load_protocol();selected=cases(config,a.stage)
    if a.execute and a.smoke_worlds:p.error('Choose execution or world-generation smoke')
    if a.stage=='confirmation' and (a.execute or a.smoke_worlds):
        if not a.candidate_lock:p.error('Confirmation requires a reviewed candidate lock; it is never a smoke target')
        candidate=json.loads(a.candidate_lock.read_text())
        if candidate.get('protocol_sha256')!=lock['protocol_sha256'] or candidate.get('mode')!=a.candidate:p.error('Candidate lock does not match mode/protocol')
        for file,digest in candidate.get('source_sha256',{}).items():
            if sha(ROOT/file)!=digest:p.error('Candidate source mismatch: '+file)
        if not candidate.get('source_sha256') or not candidate.get('actor_hashes'):p.error('Candidate lock must identify sources and actors')
        if candidate.get('confirmation_consumed',True):p.error('Candidate confirmation allocation already consumed or not explicitly reserved')
    if not (a.execute or a.smoke_worlds):
        print(json.dumps(dict(valid=True,version=config['version'],stage=a.stage,cases=len(selected),episodes_per_two_controllers=2*len(selected),executed=False),indent=2));return
    if not a.output:p.error('Output required')
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'protocol.json').write_text(json.dumps(config,indent=2)+'\n')
    from swarm_sar.learning.env import VariableSwarmRLlibEnv
    if a.smoke_worlds:
        rows=[]
        # First discovery seed only; no actor, actions, reward or confirmation maps.
        for c in selected:
            if c['seed']!=config['stages']['discovery'][0]:continue
            env=VariableSwarmRLlibEnv(env_config(config,c))
            try:
                env.reset(seed=c['seed'])
                rows.append(dict(**c,status='generated',signature=signature(env.env),victims=len(env.env.core.victims),shape=list(env.env.core.grid.shape)))
            except Exception as error:rows.append(dict(**c,status='failed',error=str(error)))
            finally:env.close()
        (a.output/'world_smoke.json').write_text(json.dumps(dict(kind='world_generation_only',rows=rows),indent=2)+'\n')
        failed=sum(r['status']=='failed' for r in rows)
        print(json.dumps(dict(worlds_generated=len(rows)-failed,worlds_failed=failed,episodes_executed=0)))
        if failed:raise SystemExit(1)
        return
    import torch
    from ray.rllib.core.rl_module.rl_module import RLModule
    from swarm_sar.learning.inference import initial_policy_state,policy_step
    from swarm_sar.learning.training import policy_mapping_fn
    from swarm_sar.learning.demonstrations import PolicyCompatibleExpert
    from visibility_frontiers import PrivateFrontierPlanner
    torch.set_num_threads(1)
    cp=ROOT/'training/runs/ppo_754k_handoff/results/gpu_continue_1m/checkpoints/step_000000753664'
    modules={n:RLModule.from_checkpoint(str(cp/'learner_group/learner/rl_module'/n)).to('cpu').eval() for n in ['rover_policy','drone_policy']}
    def actor_hashes():return {n:hashlib.sha256(torch.cat([p.detach().reshape(-1) for p in m.parameters()]).numpy().tobytes()).hexdigest() for n,m in modules.items()}
    original=actor_hashes();assert original==json.loads((cp/'parameter_hashes.json').read_text())
    if a.stage=='confirmation':
        if original!=candidate['actor_hashes']:raise ValueError('Actor differs from candidate lock')
        # Consume before any confirmation episode; even interrupted inspection is data access.
        candidate['confirmation_consumed']=True
        a.candidate_lock.write_text(json.dumps(candidate,indent=2)+'\n')
    modes=['ppo','expert']+([a.candidate] if a.candidate else []);rows=[];start=time.monotonic()
    for c in selected:
        signatures=[]
        for mode in modes:
            env=VariableSwarmRLlibEnv(env_config(config,c))
            try:
                obs,_=env.reset(seed=c['seed']);core=env.env
                expert=PolicyCompatibleExpert(core) if mode=='expert' else None
                if expert:expert.reset(c['seed'])
                signatures.append(signature(core))
                planners={agent:PrivateFrontierPlanner(mode!='square5',24 if mode=='visible24' else 5) for agent in core.agents}
                states={agent:initial_policy_state(modules[policy_mapping_fn(agent)]) for agent in core.agents} if mode=='ppo' else {}
                with gzip.open(a.output/(case_key(c)+'_'+mode+'.jsonl.gz'),'wt') as trace:
                    while env.agents:
                        if mode=='expert':actions=expert.choose_actions()
                        elif mode=='ppo':
                            actions={}
                            for agent in env.agents:actions[agent],states[agent]=policy_step(modules[policy_mapping_fn(agent)],obs[agent],None,states[agent])
                        else:actions={agent:planners[agent].choose(core,agent,config['max_steps']-core.core.step_count)[0] for agent in env.agents}
                        obs,_,_,_,_=env.step(actions)
                        if expert:expert.observations={agent:core.observe(agent) for agent in core.agents}
                        trace.write(json.dumps(dict(step=core.core.step_count,actions=actions))+'\n')
                m=env.metrics_snapshot()
                row=dict(**c,mode=mode,found=m['victims_found'],total=m['survivors_total'],coverage=m['coverage'],steps=m['step'],initial_signature=signatures[-1],
                    termination='all_found' if m['victims_found']==m['survivors_total'] else 'all_batteries_depleted' if not any(r.alive for r in core.core.robots) else 'deadline',
                    remaining_energy={r.name:r.battery for r in core.core.robots})
                rows.append(row);print(json.dumps(row),flush=True)
            except Exception as error:
                (a.output/'failure.json').write_text(json.dumps(dict(case=c,mode=mode,error=str(error),completed_rows=len(rows)),indent=2)+'\n');raise
            finally:env.close()
            assert actor_hashes()==original
            report=dict(stage=a.stage,protocol_sha256=lock['protocol_sha256'],rows=rows,actor_hashes=original,complete=False,elapsed_seconds=time.monotonic()-start)
            (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
        if len(set(signatures))!=1:raise ValueError('Initial cases differ between controllers')
    report['complete']=True;(a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
