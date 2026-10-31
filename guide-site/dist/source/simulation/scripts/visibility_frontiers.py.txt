"""Private-belief visibility proxy and separate heuristic planner experiments."""
from collections import Counter
import numpy as np
from swarm_sar.sensing.vision import bresenham_line
from swarm_sar.sim.planning import frontier_candidates
from frontier_utility import candidate_utility


def visible_unknown_gain(belief, goal, radius):
    x,y=goal;h,w=belief.shape;gain=0
    for ty in range(max(0,y-radius),min(h,y+radius+1)):
        for tx in range(max(0,x-radius),min(w,x+radius+1)):
            if belief[ty,tx]>=0:continue
            # Known walls occlude. Unknown intermediate cells can hide walls,
            # so this remains an optimistic estimate, never ground-truth gain.
            if not any(belief[py,px]==1 for px,py in bresenham_line(goal,(tx,ty))[1:-1]):gain+=1
    return gain


class PrivateFrontierPlanner:
    def __init__(self,visible=True,pool_size=5):
        self.visible=visible;self.pool_size=pool_size;self.visits=Counter();self.counts=Counter()

    def choose(self,env,agent,remaining):
        r=env._robots_by_name[agent];cfg=env.core.robot_configs[r.type]
        self.visits[r.position]+=1
        observation=env.observe(agent)
        # Same public sensor thresholds in all heuristic arms; no actor used.
        if float(observation['thermal'].max())>=.35 and float(observation['acoustic'][0])>=.08:
            self.counts['investigate']+=1;return 5,dict(reason='sensor_investigate')
        candidates=env._candidate_list(agent) if self.pool_size==5 else frontier_candidates(
            r.belief,r.position,max_candidates=self.pool_size,max_per_cluster=5,can_cross_rubble=cfg['can_cross_rubble'])
        claims=env.peer_claims(agent);ranked=[]
        for c in candidates:
            v=candidate_utility(c,r.belief,r.battery,remaining,cfg,self.visits,tuple(c['position']) in claims)
            gain=visible_unknown_gain(r.belief,tuple(c['position']),min(4,int(cfg['vision_radius']))) if self.visible else v['unknown_opportunity']
            if not v['feasible'] or gain<4:continue
            # Substitute the visibility estimate without changing other penalties.
            score=v['score']*gain/max(1,v['unknown_opportunity'])
            ranked.append((score,c,v,gain))
        self.counts['candidate_evaluations']+=len(candidates)
        for score,c,v,gain in sorted(ranked,key=lambda t:(-t[0],tuple(t[1]['position']))):
            old=env._active_goals.get(agent)
            env.set_active_goal(agent,tuple(c['position']))
            offered=env._candidate_list(agent);mask=env.observe(agent)['action_mask']
            slot=next((i for i,t in enumerate(offered[:5]) if tuple(t['position'])==tuple(c['position']) and mask[i]>0),None)
            if slot is not None:
                self.counts['frontier_moves']+=1
                return slot,dict(reason='heuristic_frontier',goal=c['position'],gain=gain,square_gain=v['unknown_opportunity'],score=score,path_energy=v['path_energy'],pool=len(candidates))
            env.set_active_goal(agent,old)
        self.counts['hold_no_legal_affordable_gain']+=1
        return 6,dict(reason='no_legal_affordable_gain',pool=len(candidates))
