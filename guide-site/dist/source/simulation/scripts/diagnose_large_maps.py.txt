"""Small inference-only paired diagnosis; instrumentation stays outside training sources."""
from collections import Counter
from pathlib import Path
import argparse, gzip, hashlib, json, subprocess, time
import numpy as np
import torch
from ray.rllib.core.rl_module.rl_module import RLModule
from swarm_sar.learning.env import VariableSwarmRLlibEnv
from swarm_sar.learning.demonstrations import PolicyCompatibleExpert
from swarm_sar.learning.inference import initial_policy_state, policy_step
from swarm_sar.learning.training import policy_mapping_fn
from swarm_sar.validation.seeds import load_seed_splits


def run(modules, size, seed, controller, horizon, energy, output, stochastic=False, intervention=None):
    adapter=VariableSwarmRLlibEnv(dict(seed=seed,curriculum=False,world_sizes=[size],max_steps=horizon,
        network_enabled=True,fixed_team_profile={'rover':2,'drone':2},final_team_profiles=[{'rover':2,'drone':2}],
        world_overrides=dict(layout='maze',footprint='full',max_generation_retries=100)))
    for cfg in adapter.base_robots.values():cfg['battery']*=energy
    obs,_=adapter.reset(seed=seed); env=adapter.env
    expert=PolicyCompatibleExpert(env) if controller=='expert' else None
    if expert:
        expert.reset(seed); obs={a:adapter.env.observe(a) for a in env.agents}
    signature=hashlib.sha256(env.core.grid.tobytes()+json.dumps(env.core.victims,sort_keys=True).encode()).hexdigest()
    counts={a:Counter() for a in env.agents}; visited={a:Counter([env._robots_by_name[a].position]) for a in env.agents}
    longest={a:0 for a in env.agents}; stuck={a:0 for a in env.agents}; merges=Counter(); last_discovery=0
    requested={}; filtered={}; original_shield=env._safety_filter_movements
    def shield(actions):
        requested.clear(); requested.update(actions)
        result=original_shield(actions); filtered.clear(); filtered.update(result); return result
    env._safety_filter_movements=shield
    original_drain=env.network.drain
    def drain(recipient):
        messages=original_drain(recipient)
        limit=env.core.sim_config['network_transform_uncertainty_max']
        for m in messages:
            if not m.payload.get('map_cells'):continue
            reasons=[]
            if m.frame_id!='common_entry_v1':reasons.append('frame')
            if m.pose_uncertainty>limit:reasons.append('sender_uncertainty')
            if env._robots_by_name[recipient].odom_uncertainty>limit:reasons.append('receiver_uncertainty')
            merges['refused' if reasons else 'accepted']+=1
            for reason in reasons:merges[reason]+=1
        return messages
    env.network.drain=drain
    states={a:initial_policy_state(modules[policy_mapping_fn(a)]) for a in env.agents}
    rng=np.random.default_rng(seed^0x5033)
    from goal_governor import GoalGovernor
    from frontier_utility import FrontierUtility
    factory=FrontierUtility if intervention in ('utility','hold_release') else GoalGovernor
    governors={a:factory(intervention) for a in env.agents} if intervention else {}
    name=f'{size}_{seed}_{controller}_h{horizon}_e{energy:g}'+('_'+intervention if intervention else '')
    with gzip.open(output/(name+'.jsonl.gz'),'wt') as trace:
        while env.agents:
            raw={a:env.observe(a) for a in env.agents}
            if expert:actions=expert.choose_actions()
            else:
                actions={}
                for a in env.agents:actions[a],states[a]=policy_step(modules[policy_mapping_fn(a)],obs[a],rng if stochastic else None,states[a])
            proposed=dict(actions); override_reasons={}
            for a,governor in governors.items():
                if a in actions:
                    robot=env._robots_by_name[a]
                    arguments=dict(position=robot.position,candidates=env._candidate_list(a),mask=raw[a]['action_mask'],step=env.core.step_count)
                    if hasattr(governor,'choose_context'):
                        actions[a],override_reasons[a]=governor.choose_context(actions[a],**arguments,belief=robot.belief,battery=robot.battery,
                            remaining_steps=horizon-env.core.step_count,config=env.core.robot_configs[robot.type],claims=env.peer_claims(a))
                    else:actions[a],override_reasons[a]=governor.choose(actions[a],**arguments)
            before={a:(env._robots_by_name[a].position,env._active_goals.get(a)) for a in env.agents}
            detail={}
            for a,action in actions.items():
                candidates=env._candidate_list(a); legal=int(np.count_nonzero(raw[a]['action_mask'][:5])); c=counts[a]
                c['decisions']+=1; c['candidate_slots']+=len(candidates)
                if legal==0:c['no_legal_frontier']+=1
                if len(candidates)==5:c['all_five_slots_used']+=1
                c['distance_features_saturated']+=sum(float(v[2])>=1. for v in raw[a]['frontier_features'] if v[4]>0)
                if action==6:c['hold_with_legal_frontier' if legal else 'hold_without_legal_frontier']+=1
                if action==5:c['investigate']+=1
                goal=tuple(candidates[action]['position']) if action<5 and action<len(candidates) else None
                old=before[a][1]
                if goal is not None and old is not None and goal!=old:c['goal_switch_before_arrival']+=1
                detail[a]=dict(utility_diagnostics=getattr(governors.get(a),'last_diagnostics',None),proposed_policy_action=int(proposed[a]),override_reason=override_reasons.get(a,'none'),action=int(action),legal_frontiers=legal,candidates=[list(x['position']) for x in candidates],goal=goal)
            obs,_,_,_,_=adapter.step(actions)
            if expert:expert.observations={a:env.observe(a) for a in env.agents}
            found=int(env.core.metrics.victims_found)
            if found>getattr(run,'last_found',0):last_discovery=env.core.step_count
            run.last_found=found
            for a,d in detail.items():
                robot=env._robots_by_name[a]; c=counts[a]; moved=robot.position!=before[a][0]
                if requested[robot.id]!=filtered[robot.id]:c['shield_changed_move']+=1
                if requested[robot.id] and not filtered[robot.id]:c['shield_stopped_move']+=1
                if moved:
                    c['moves']+=1
                    if visited[a][robot.position]:c['moves_to_previously_visited_cell']+=1
                    visited[a][robot.position]+=1; stuck[a]=0
                else:
                    c['stationary']+=1; stuck[a]+=1; longest[a]=max(longest[a],stuck[a])
                d.update(position=list(robot.position),battery=float(robot.battery),uncertainty=float(robot.odom_uncertainty),
                    requested_move=int(requested[robot.id]),filtered_move=int(filtered[robot.id]),moved=moved)
            trace.write(json.dumps(dict(step=env.core.step_count,found=found,agents=detail))+'\n')
    metrics=adapter.metrics_snapshot(); found=int(metrics['victims_found']); total=int(metrics['survivors_total'])
    reason='all_survivors_found' if found==total else 'all_batteries_depleted' if not any(r.alive for r in env.core.robots) else 'deadline'
    result=dict(intervention=intervention,governor_counts={a:dict(g.counts) for a,g in governors.items()},case=name,size=size,seed=seed,controller=controller,max_steps=horizon,energy_multiplier=energy,
        initial_map_and_victims_sha256=signature,steps=metrics['step'],found=found,total=total,coverage=metrics['coverage'],
        termination=reason,steps_since_last_discovery=int(metrics['step'])-last_discovery,network=env.network_metrics(),
        merge_reasons=dict(merges),agents={a:dict(counts[a],unique_positions=len(visited[a]),longest_stationary_run=longest[a],
          final_battery=float(r.battery),alive=bool(r.alive),final_uncertainty=float(r.odom_uncertainty)) for a,r in env._robots_by_name.items()},
        battery_depletion_events=[e for e in env.core.events if e['event']=='battery_depleted'])
    adapter.close(); run.last_found=0
    print(json.dumps({k:result[k] for k in ['case','steps','found','total','coverage','termination']}),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--stochastic',action='store_true')
    args=p.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    assert {10000,10001}<=set(load_seed_splits()['development'])
    torch.set_num_threads(1)
    checkpoint=Path('training/runs/ppo_754k_handoff/results/gpu_continue_1m/checkpoints/step_000000753664').resolve()
    modules={name:RLModule.from_checkpoint(str(checkpoint/'learner_group/learner/rl_module'/name)).to('cpu').eval() for name in ['rover_policy','drone_policy']}
    hashes={name:hashlib.sha256(torch.cat([p.detach().reshape(-1) for p in m.parameters()]).numpy().tobytes()).hexdigest() for name,m in modules.items()}
    assert hashes==json.loads((checkpoint/'parameter_hashes.json').read_text())
    cases=[(size,seed,400,1) for size in [32,56] for seed in [10000,10001]]
    cases += [(56,10001,800,1),(56,10001,400,2),(56,10001,800,2)]
    results=[]; started=time.monotonic()
    for size,seed,horizon,energy in cases:
        pair=[run(modules,size,seed,kind,horizon,energy,args.output,args.stochastic) for kind in ['ppo','expert']]
        assert pair[0]['initial_map_and_victims_sha256']==pair[1]['initial_map_and_victims_sha256']
        results.extend(pair)
        report=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),policy_hashes=hashes,
            seeds=[10000,10001],seed_split='development',inference='stochastic exploratory' if args.stochastic else 'deterministic; same mode as saved review',
            elapsed_seconds=time.monotonic()-started,results=results,
            limits='Small diagnostic sample, not a new benchmark. More time changes mission-progress input. Energy changes battery observations. Counterfactuals are out-of-distribution diagnostics.')
        (args.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
