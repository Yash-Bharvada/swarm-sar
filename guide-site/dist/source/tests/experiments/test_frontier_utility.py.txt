import sys
from pathlib import Path
from collections import Counter
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'simulation/scripts'))
from frontier_utility import FrontierUtility,candidate_utility

CFG=dict(vision_radius=4,move_cost=1.,rubble_cost=2.)

def setup():
    b=np.full((12,12),-1);b[0,:6]=0
    c=[dict(position=(2,0),path=[(0,0),(1,0),(2,0)],distance=2)]
    return b,c

def test_energy_budget_and_horizon_admission_are_explicit():
    b,c=setup()
    v=candidate_utility(c[0],b,10,10,CFG,Counter())
    assert v['feasible'] and v['path_energy']==2
    assert not candidate_utility(c[0],b,1,10,CFG,Counter())['feasible']
    assert not candidate_utility(c[0],b,10,1,CFG,Counter())['feasible']
    b[0,1]=2
    assert candidate_utility(c[0],b,10,10,CFG,Counter())['path_energy']==3

def choose(g,action,mask=(1,0,0,0,0,1,1),battery=10):
    b,c=setup()
    return g.choose_context(action,position=(0,0),candidates=c,mask=mask,step=0,belief=b,battery=battery,remaining_steps=10,config=CFG,claims=set())

def test_hold_release_is_bounded_and_preserves_investigation():
    g=FrontierUtility('hold_release')
    for _ in range(3):assert choose(g,6)[0]==6
    assert choose(g,6)==(0,'release_prolonged_hold')
    assert choose(g,5)[0]==5
    assert choose(g,6)[0]==6

def test_no_override_without_legal_affordable_opportunity():
    for mask,battery in [((0,0,0,0,0,1,1),10),((1,0,0,0,0,1,1),1)]:
        g=FrontierUtility('utility')
        for _ in range(5):assert choose(g,6,mask,battery)[0]==6

def test_visits_and_peer_claims_penalize_but_never_add_information():
    b,c=setup();baseline=candidate_utility(c[0],b,10,10,CFG,Counter())
    other=candidate_utility(c[0],b,10,10,CFG,Counter({(2,0):1}),True)
    assert other['unknown_opportunity']==baseline['unknown_opportunity']
    assert other['score']==baseline['score']/4
