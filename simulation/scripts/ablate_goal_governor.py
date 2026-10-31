"""Controlled frozen-PPO goal-persistence/loop ablation; CPU inference only."""
import argparse, hashlib, json, subprocess, time
from pathlib import Path
import torch
from ray.rllib.core.rl_module.rl_module import RLModule
from diagnose_large_maps import run
from swarm_sar.validation.seeds import load_seed_splits

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--seeds',type=int,nargs='+',default=[10000,10001])
p.add_argument('--sizes',type=int,nargs='+',default=[32,56])
p.add_argument('--modes',nargs='+',choices=['baseline','persistence','loop','combined','utility','hold_release'],default=['baseline','persistence','loop','combined'])
a=p.parse_args()
if not set(a.seeds)<=set(load_seed_splits()['development']):p.error('Development seeds only')
a.output.mkdir(parents=True,exist_ok=False);torch.set_num_threads(1)
checkpoint=Path('training/runs/ppo_754k_handoff/results/gpu_continue_1m/checkpoints/step_000000753664').resolve()
modules={n:RLModule.from_checkpoint(str(checkpoint/'learner_group/learner/rl_module'/n)).to('cpu').eval() for n in ['rover_policy','drone_policy']}
def hashes():return {n:hashlib.sha256(torch.cat([p.detach().reshape(-1) for p in m.parameters()]).numpy().tobytes()).hexdigest() for n,m in modules.items()}
before=hashes();assert before==json.loads((checkpoint/'parameter_hashes.json').read_text())
results=[];started=time.monotonic()
for size in a.sizes:
 for seed in a.seeds:
  signatures=[]
  for selected_mode in a.modes:
   mode=None if selected_mode=='baseline' else selected_mode
   row=run(modules,size,seed,'ppo',400,1,a.output,intervention=mode)
   signatures.append(row['initial_map_and_victims_sha256']);results.append(row)
  assert len(set(signatures))==1
  assert hashes()==before,'Actor changed'
  report=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    policy_hashes=before,actor_unchanged=True,elapsed_seconds=time.monotonic()-started,results=results,
    config=dict(commitment_steps=12,stall_release_steps=4,loop_window_steps=16,repeated_directed_edge_threshold=2,deadline=400,battery_multiplier=1,utility_gain_radius_cap=4,utility_min_unknown=4,utility_battery_fraction=.8,hold_release_after=4),
    source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).with_name('goal_governor.py'),Path(__file__).with_name('diagnose_large_maps.py'),Path(__file__).with_name('frontier_utility.py')]},
    limits='Development-only small paired ablation. Overrides are heuristic decisions, not new learned behavior. Existing simulator-informed action masks/shield retained. No retraining or ROS integration.')
  (a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
