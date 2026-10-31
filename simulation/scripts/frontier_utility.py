"""Opt-in heuristic ablation over unchanged PPO candidate slots, not new learning."""
from collections import Counter
import numpy as np


def candidate_utility(candidate, belief, battery, remaining_steps, config, visits, claimed=False):
    path=candidate['path']; goal=tuple(candidate['position'])
    radius=min(4,int(config['vision_radius']))
    x,y=goal; h,w=belief.shape
    # Unknown-cell opportunity proxy, not predicted visibility: walls may occlude.
    gain=int(np.count_nonzero(belief[max(0,y-radius):min(h,y+radius+1),max(0,x-radius):min(w,x+radius+1)]<0))
    energy=sum(float(config['rubble_cost'] if belief[p[1],p[0]]==2 else config['move_cost']) for p in path[1:])
    feasible=len(path)>=2 and energy<=.8*battery and len(path)-1<=remaining_steps
    score=gain/((1+energy)*(1+visits.get(goal,0))*(2 if claimed else 1)) if feasible else -1.
    return dict(score=score,unknown_opportunity=gain,path_energy=energy,feasible=feasible,
                goal_visits=visits.get(goal,0),peer_claimed=claimed)


class FrontierUtility:
    def __init__(self, mode):
        self.mode=mode;self.counts=Counter();self.visits=Counter();self.holds=0;self.last_diagnostics={}

    def choose_context(self, proposed, *, position, candidates, mask, step, belief, battery, remaining_steps, config, claims):
        del step
        self.visits[tuple(position)]+=1;self.holds=self.holds+1 if proposed==6 else 0
        utilities={i:candidate_utility(c,belief,battery,remaining_steps,config,self.visits,tuple(c['position']) in claims)
                   for i,c in enumerate(candidates[:5]) if mask[i]>0}
        viable=[i for i,v in utilities.items() if v['feasible'] and v['unknown_opportunity']>=4]
        best=max(viable,key=lambda i:(utilities[i]['score'],-i)) if viable else None
        self.last_diagnostics=dict(utilities=utilities,consecutive_proposed_holds=self.holds)
        if proposed==6:
            self.counts['proposed_holds']+=1
            self.counts['hold_with_affordable_opportunity' if viable else 'hold_without_affordable_opportunity']+=1
        action=proposed;reason='policy'
        if best is not None and proposed==6 and self.holds>=4:
            action=best;reason='release_prolonged_hold'
        elif best is not None and proposed<5 and self.mode=='utility':
            action=best;reason='utility_frontier_choice'
        # INVESTIGATE always survives, and no non-movement action is suppressed
        # without an affordable, legal unknown-space opportunity.
        self.counts['decisions']+=1
        if action!=proposed:self.counts['overrides']+=1;self.counts[reason]+=1
        return action,reason
