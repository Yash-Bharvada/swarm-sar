import numpy as np

from swarm_sar.baselines.decentralized import DecentralizedFrontierController
from swarm_sar.sim.env import DisasterResponseParallelEnv
from swarm_sar.utils.config import load_config


def network_env(loss=0.0):
    sim = load_config("configs/sim.yaml")
    sim.update(
        network_enabled=True,
        network_packet_loss=loss,
        network_delay_steps=[1, 2],
        investigate_confirms_victims=True,
        frontier_samples_per_cluster=5,
    )
    return DisasterResponseParallelEnv(sim_config=sim)


def test_controller_has_only_local_goals_and_no_reservation_table():
    env = network_env()
    controller = DecentralizedFrontierController(env)
    controller.reset(30)
    actions = controller.choose_actions()
    assert set(actions) == set(env.agents)
    assert not hasattr(controller, "reservations")
    assert set(controller.local_goals) <= set(env.agents)
    env.close()


def test_weak_thermal_requires_independent_acoustic_corroboration():
    env = network_env()
    controller = DecentralizedFrontierController(env)
    controller.reset(30)
    agent = env.agents[0]
    controller.observations[agent]["thermal"] = np.array(
        [0.18, 0.0, 0.0, 0.0], dtype=np.float32
    )
    controller.observations[agent]["acoustic"] = np.array([0.05], dtype=np.float32)
    assert not controller._should_investigate(agent)
    controller.observations[agent]["acoustic"] = np.array([0.25], dtype=np.float32)
    assert controller._should_investigate(agent)
    env.close()


def test_rendezvous_branch_owner_is_stable_and_reassigns_missing_peer():
    position = (41, 73)
    participants = ("drone_2", "rover_0", "rover_1")
    owner = DecentralizedFrontierController._branch_owner(position, participants)
    assert owner == DecentralizedFrontierController._branch_owner(position, participants)
    remaining = tuple(agent for agent in participants if agent != owner)
    assert DecentralizedFrontierController._branch_owner(position, remaining) in remaining


def test_state_messages_carry_required_step4_fields():
    env = network_env()
    env.reset(seed=31)
    for _ in range(3):
        env.step({agent: 6 for agent in env.agents})
    messages = env.network.peer_messages(env.agents[0], env.core.step_count)
    assert messages
    message = messages[0]
    assert message.sender_id and message.seq >= 0
    assert message.frame_id == "common_entry_v1"
    assert message.pose_uncertainty >= 0
    assert {"goal", "evidence", "graph_delta", "map_cells"} <= set(message.payload)
    env.close()


def test_controller_replays_identically_with_loss_and_delay():
    first_env, second_env = network_env(0.30), network_env(0.30)
    first = DecentralizedFrontierController(first_env)
    second = DecentralizedFrontierController(second_env)
    first_summary = first.run_episode(300)
    second_summary = second.run_episode(300)
    assert first_summary == second_summary
    assert first.events == second.events
    first_env.close()
    second_env.close()


def test_controller_retains_local_autonomy_without_network():
    sim = load_config("configs/sim.yaml")
    sim.update(investigate_confirms_victims=True, frontier_samples_per_cluster=5)
    env = DisasterResponseParallelEnv(sim_config=sim)
    controller = DecentralizedFrontierController(env)
    controller.reset(32)
    for _ in range(10):
        controller.step()
    assert env.core.step_count == 10
    assert controller.local_goals
    assert not env.network_metrics()["enabled"]
    env.close()


def test_controller_never_selects_a_masked_policy_action():
    env = network_env(loss=0.30)
    controller = DecentralizedFrontierController(env)
    controller.reset(33)
    for _ in range(100):
        if not env.agents:
            break
        actions = controller.choose_actions()
        assert all(
            controller.observations[agent]["action_mask"][action] > 0
            for agent, action in actions.items()
        )
        result = env.step(actions)
        controller.observations = result[0]
    env.close()
