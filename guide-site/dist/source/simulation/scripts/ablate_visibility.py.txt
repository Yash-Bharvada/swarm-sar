"""Predeclared development-only comparison; do not tune on resulting seeds."""
import argparse,hashlib,json,time,subprocess,gzip
from pathlib import Path
import numpy as np
import torch
from ray.rllib.core.rl_module.rl_module import RLModule
from swarm_sar.learning.env import VariableSwarmRLlibEnv
from swarm_sar.learning.inference import initial_policy_state,policy_step
from swarm_sar.learning.training import policy_mapping_fn
from swarm_sar.validation.seeds import load_seed_splits
from visibility_frontiers import PrivateFrontierPlanner

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
cases=[(s,seed) for s in (32,56) for seed in (10008,10009)]+[(56,10010),(56,10011)]
modes=['ppo','square5','visible5','visible24']
plan=dict(cases=cases,modes=modes,max_steps=400,battery_multiplier=1,team={'rover':2,'drone':2},gain_radius_cap=4,min_gain=4,battery_fraction=.8,
    investigate_thresholds=dict(thermal=.35,acoustic=.08),settings_frozen_before_run=True,
    selection_rule='No mode promoted from these cases; no within-run retuning. Final seeds remain sealed.',
    limits='Additional development seeds, not guaranteed historically unseen in every experiment. Square known-wall ray estimate remains optimistic through unknown cells. Heuristic arms never invoke PPO.')
assert {seed for _,seed in cases}<=set(load_seed_splits()['development'])
(a.output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
torch.set_num_threads(1);cp=Path('training/runs/ppo_754k_handoff/results/gpu_continue_1m/checkpoints/step_000000753664').resolve()
modules={n:RLModule.from_checkpoint(str(cp/'learner_group/learner/rl_module'/n)).to('cpu').eval() for n in ['rover_policy','drone_policy']}
def hashes():return {n:hashlib.sha256(torch.cat([p.detach().reshape(-1) for p in m.parameters()]).numpy().tobytes()).hexdigest() for n,m in modules.items()}
original=hashes();assert original==json.loads((cp/'parameter_hashes.json').read_text())
rows=[];started=time.monotonic()
for size,seed in cases:
 signatures=[]
 for mode in modes:
  adapter=VariableSwarmRLlibEnv(dict(curriculum=False,world_sizes=[size],max_steps=400,network_enabled=True,
    fixed_team_profile={'rover':2,'drone':2},final_team_profiles=[{'rover':2,'drone':2}],
    world_overrides=dict(layout='maze',footprint='full',max_generation_retries=100)))
  obs,_=adapter.reset(seed=seed);env=adapter.env
  signature=hashlib.sha256(env.core.grid.tobytes()+json.dumps(env.core.victims,sort_keys=True).encode()).hexdigest();signatures.append(signature)
  planners={agent:PrivateFrontierPlanner(mode!='square5',24 if mode=='visible24' else 5) for agent in env.agents}
  states={agent:initial_policy_state(modules[policy_mapping_fn(agent)]) for agent in env.agents} if mode=='ppo' else {}
  with gzip.open(a.output/f'{size}_{seed}_{mode}.jsonl.gz','wt') as f:
   while adapter.agents:
    actions={};details={}
    for agent in adapter.agents:
     if mode=='ppo':actions[agent],states[agent]=policy_step(modules[policy_mapping_fn(agent)],obs[agent],None,states[agent]);details[agent]={'reason':'ppo'}
     else:actions[agent],details[agent]=planners[agent].choose(env,agent,400-env.core.step_count)
    obs,_,_,_,_=adapter.step(actions)
    f.write(json.dumps(dict(step=env.core.step_count,actions=actions,decisions=details))+'\n')
  m=adapter.metrics_snapshot();reason='all_found' if m['victims_found']==m['survivors_total'] else 'all_batteries_depleted' if not any(r.alive for r in env.core.robots) else 'deadline'
  row=dict(size=size,seed=seed,mode=mode,found=m['victims_found'],total=m['survivors_total'],coverage=m['coverage'],steps=m['step'],termination=reason,
    initial_signature=signature,planner_counts={agent:dict(v.counts) for agent,v in planners.items()} if mode!='ppo' else {})
  rows.append(row);adapter.close();print(json.dumps(row),flush=True)
 assert len(set(signatures))==1;assert hashes()==original
 report=dict(plan=plan,rows=rows,actor_hashes=original,actor_unchanged=True,paired_initial_states_equal=True,elapsed_seconds=time.monotonic()-started,
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('visibility_frontiers.py'),Path(__file__).with_name('frontier_utility.py')]})
 (a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
