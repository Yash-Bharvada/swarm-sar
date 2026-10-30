"""Geometry and failure-mode tests that need no ROS installation."""
import copy
import math
from pathlib import Path
import sys
import numpy as np
import pytest
import yaml

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'simulation/ros2_ws/src/swarm_sar_control'))
from swarm_sar_control.slam_support import GridSpec, PeerKnowledge, RadioBudget, project_occupancy, frontier_graph, slam_bridges

SPEC=GridSpec(8,8,1.,0.,0.)

def packet(**changes):
    p=dict(schema=1,run='session-a',spec=SPEC.payload(),uncertainty_m=.25,revision=1,chunk=0,chunks=1,cells=[[1,2,100]],frontiers=[])
    p.update(changes); return p

def accept(k,p=None,seq=1,now=1.,expires=9.,frame='map'):
    return k.accept('rover_1',seq,expires,frame,p or packet(),now)

def test_reprojection_respects_origin_rotation_and_start_alignment():
    grid=project_occupancy([100,0],2,1,1.,(0.,0.,math.pi/2),(3.,1.,0.),SPEC)
    assert grid[1,2]==100 and grid[2,2]==0
    assert np.count_nonzero(grid>=0)==2

def test_coarse_collision_keeps_occupied_and_unknown_does_not_erase():
    g=project_occupancy([100,0,-1,40],4,1,.2,(0.,0.,0.),(0.,0.,0.),SPEC)
    assert g[0,0]==100 and np.count_nonzero(g>=0)==1

@pytest.mark.parametrize('data,width,height,res', [([0],2,2,1.),([101],1,1,1.),([0],1,1,0.)])
def test_bad_source_grids_rejected(data,width,height,res):
    with pytest.raises(ValueError):project_occupancy(data,width,height,res,(0.,0.,0.),(0.,0.,0.),SPEC)

def test_out_of_order_chunks_apply_atomically_and_duplicate_is_ignored():
    k=PeerKnowledge(SPEC)
    assert accept(k,packet(chunk=1,chunks=2,cells=[[3,4,0]]))=='buffered'
    assert not k.layers
    assert accept(k,packet(chunk=1,chunks=2,cells=[[3,4,0]]))=='duplicate'
    assert accept(k,packet(chunk=0,chunks=2,frontiers=[dict(id='f',x=1.,y=2.)]),seq=2)=='applied'
    assert k.layers['rover_1'][2,1]==100 and k.layers['rover_1'][4,3]==0
    assert k.topologies['rover_1'][0]['id']=='f'

def test_repair_finishes_missing_chunk_and_full_snapshot_removes_obsolete_cells():
    k=PeerKnowledge(SPEC); accept(k)
    assert accept(k,packet(revision=2,chunks=2,cells=[[0,0,0]]),seq=2)=='buffered'
    assert k.layers['rover_1'][2,1]==100
    assert accept(k,packet(revision=2,chunk=1,chunks=2,cells=[[7,7,100]]),seq=3)=='applied'
    assert k.layers['rover_1'][2,1]==-1 and k.layers['rover_1'][7,7]==100
    assert accept(k,seq=4)=='stale_revision'

@pytest.mark.parametrize('payload,frame,expires,expected',[(packet(), 'wrong',9.,'unaligned'),(packet(uncertainty_m=3.),'map',9.,'uncertain'),(packet(),'map',1.,'expired'),(packet(cells=[[999,0,0]]),'map',9.,'malformed'),(packet(schema=2),'map',9.,'schema')])
def test_invalid_messages_never_mutate_knowledge(payload,frame,expires,expected):
    k=PeerKnowledge(SPEC)
    assert accept(k,payload,frame=frame,expires=expires)==expected
    assert not k.layers and not k.pending

def test_invalid_new_session_cannot_erase_valid_layer_or_allow_old_session_replay():
    k=PeerKnowledge(SPEC);accept(k)
    assert accept(k,packet(run='b',cells=[[8,0,0]]),seq=0)=='malformed'
    assert k.sessions['rover_1']=='session-a' and 'rover_1' in k.layers
    assert accept(k,packet(run='b',cells=[[0,0,0]]),seq=0)=='applied'
    assert accept(k,seq=2)=='old_session'

def test_new_session_partial_snapshot_clears_old_layer_metadata_atomically():
    k=PeerKnowledge(SPEC);accept(k)
    assert accept(k,packet(run='b',chunks=2),seq=0)=='buffered'
    assert 'rover_1' not in k.layers and 'rover_1' not in k.layer_age and 'rover_1' not in k.revisions

def test_peer_knowledge_does_not_modify_local_or_override_its_cells():
    k=PeerKnowledge(SPEC);accept(k)
    local=np.full((8,8),-1,dtype=np.int8); local[2,1]=0
    original=local.copy(); combined=k.combined(local)
    assert combined[2,1]==0 and k.peer_only(local)[2,1]==-1
    np.testing.assert_array_equal(local,original)

def test_incomplete_snapshot_and_claim_leases_expire_but_observed_map_remains():
    k=PeerKnowledge(SPEC,assembly_timeout=2.);accept(k)
    accept(k,packet(revision=2,chunks=2),seq=2)
    assert k.accept_claim('rover_1','map',dict(run='session-a',spec=SPEC.payload(),goal=[1.,2.]),3.,1.)=='claim_applied'
    k.expire(4.)
    assert not k.pending and not k.claims and 'rover_1' in k.layers

def test_selective_repair_recovers_snapshot_after_deterministic_packet_loss():
    k=PeerKnowledge(SPEC); sequence=0
    # Lose every third initial packet, then send only the actual missing chunks.
    for index in range(16):
        if index%3==0:continue
        sequence+=1
        accept(k,packet(chunk=index,chunks=16,cells=[[index%8,index//8,0]]),seq=sequence)
    assert not k.layers
    pending=k.pending['rover_1']
    missing=[i for i in range(16) if i not in pending['parts']]
    for index in missing:
        sequence+=1
        accept(k,packet(chunk=index,chunks=16,cells=[[index%8,index//8,0]]),seq=sequence)
    assert np.count_nonzero(k.layers['rover_1']>=0)==16

def test_bandwidth_is_shared_by_sender_and_never_refills_on_backward_time():
    b=RadioBudget(10,10)
    assert b.take('a',8,5.)
    assert not b.take('a',4,5.)
    assert not b.take('a',4,4.)
    assert b.take('b',10,5.)
    assert b.take('a',4,6.)

def test_stale_claim_cannot_override_new_intent_or_reserve_after_expiry():
    k=PeerKnowledge(SPEC);accept(k)
    p=dict(run='session-a',spec=SPEC.payload(),goal=[1.,2.])
    assert k.accept_claim('rover_1','map',p,8.,1.,sequence=10)=='claim_applied'
    assert k.accept_claim('rover_1','map',{**p,'goal':[3.,4.]},8.,2.,sequence=9)=='duplicate'
    assert k.claims['rover_1'][0]==[1.,2.]
    k.expire(8.); assert not k.claims

def test_bridge_excludes_truth_tf_and_preserves_truth_only_on_diagnostic_topic():
    entries=yaml.safe_load((ROOT/'simulation/ros2_ws/src/swarm_sar_gazebo/config/ros_gz_bridge.yaml').read_text())
    original=copy.deepcopy(entries); result=slam_bridges(entries,['rover_0','drone_0'],['rover_0'])
    assert entries==original
    assert not any(b['gz_topic_name']=='/rover_0/tf' for b in result)
    assert any(b['gz_topic_name']=='/rover_0/wheel_tf' and b['ros_topic_name']=='/tf' for b in result)
    assert next(b for b in result if b['gz_topic_name']=='/rover_0/odom')['ros_topic_name']=='/rover_0/ground_truth/odom'
    assert not any('rover_1' in b['gz_topic_name'] for b in result)

def test_frontier_components_do_not_claim_unproven_traversability_edges():
    local=np.full((8,8),-1,dtype=np.int8); local[2:5,2:5]=0
    nodes=frontier_graph(local,SPEC)
    assert nodes and all(2<=n['x']<5 and 2<=n['y']<5 for n in nodes)
