import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'simulation/scripts'))
from visibility_frontiers import visible_unknown_gain,PrivateFrontierPlanner
from swarm_sar.sim.planning import frontier_candidates


def test_known_wall_blocks_unknown_opportunity_but_unknown_is_not_truth():
    belief=np.zeros((7,7),dtype=int);belief[:,4:]=-1;belief[:,3]=1
    assert visible_unknown_gain(belief,(1,3),4)==0
    belief[:,3]=0
    assert visible_unknown_gain(belief,(1,3),4)==14
    # Unknown cells are not magically identified as walls; estimate is optimistic.
    belief[:,3]=-1
    assert visible_unknown_gain(belief,(1,3),4)==21


def test_gain_clips_at_bounds_and_never_mutates_private_belief():
    belief=np.full((4,4),-1);belief[0,0]=0;copy=belief.copy()
    assert visible_unknown_gain(belief,(0,0),2)==8
    np.testing.assert_array_equal(belief,copy)


def test_wider_candidate_pool_only_contains_locally_known_reachable_routes():
    belief=np.full((30,30),-1);belief[3:27,3:27]=0
    small=frontier_candidates(belief,(15,15),max_candidates=5,max_per_cluster=5)
    large=frontier_candidates(belief,(15,15),max_candidates=24,max_per_cluster=5)
    assert len(large)>=len(small)
    for c in large:
        assert c['path'][0]==(15,15) and c['path'][-1]==c['position']
        assert all(belief[y,x]==0 for x,y in c['path'])


def test_planner_history_is_per_robot():
    a,b=PrivateFrontierPlanner(),PrivateFrontierPlanner()
    a.visits[(1,2)]+=3
    assert b.visits[(1,2)]==0
