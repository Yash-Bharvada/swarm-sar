"""Decision-boundary checks for opt-in experimental overrides."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'simulation/scripts'))
from goal_governor import GoalGovernor


def candidates():
    return [dict(position=(4,0),path=[(0,0),(1,0),(4,0)],distance=4),
            dict(position=(0,4),path=[(0,0),(0,1),(0,4)],distance=4)]


def choose(g,action,step=0,mask=(1,1,0,0,0,1,1),position=(0,0)):
    return g.choose(action,position=position,candidates=candidates(),mask=mask,step=step)


def test_commitment_is_by_goal_identity_and_preserves_investigate_and_hold():
    g=GoalGovernor('persistence');choose(g,0)
    assert choose(g,1,1)==(0,'goal_persistence')
    assert choose(g,5,2)[0]==5
    assert choose(g,6,3)[0]==6
    # Candidate ordering changes; the remembered goal is found by coordinates.
    assert g.choose(0,position=(1,0),candidates=list(reversed(candidates())),mask=[1]*7,step=4)[0]==1


def test_commitment_expires_and_releases_stalled_or_masked_goal():
    g=GoalGovernor('persistence');choose(g,0)
    assert choose(g,1,12)[0]==1
    g=GoalGovernor('persistence');choose(g,0)
    assert choose(g,1,1,mask=(0,1,0,0,0,1,1))[0]==1
    g=GoalGovernor('persistence');choose(g,0)
    for t in range(1,4):choose(g,1,t)
    assert choose(g,1,4)[0]==1


def test_loop_escape_requires_repeated_edge_and_a_legal_alternative():
    g=GoalGovernor('loop')
    g.positions.extend([(0,0),(1,0),(0,0),(1,0)])
    assert choose(g,0)==(1,'loop_escape')
    g=GoalGovernor('loop');g.positions.extend([(0,0),(1,0),(0,0),(1,0)])
    assert choose(g,0,mask=(1,0,0,0,0,1,1))[0]==0
    assert g.counts['loop_without_alternative']==1


def test_state_is_private_and_inputs_are_not_modified():
    a,b=GoalGovernor('persistence'),GoalGovernor('persistence')
    choose(a,0)
    assert choose(b,1)[0]==1
    c=candidates(); original=repr(c)
    a.choose(1,position=(0,0),candidates=c,mask=[1]*7,step=1)
    assert repr(c)==original
