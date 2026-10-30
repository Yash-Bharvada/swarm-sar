"""Run the selected recurrent PPO policies and export an actual mission as a GIF.

Inference only; uses development seeds and leaves the audited training sources alone.
Run from the repository root. --live requires a desktop display.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def checkpoint_digest(checkpoint: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(checkpoint.rglob('*')):
        if path.is_file():
            digest.update(path.relative_to(checkpoint).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, default=Path('training/runs/ppo_754k_handoff/results/gpu_continue_1m/checkpoints/step_000000753664'))
    parser.add_argument('--seed', type=int, default=10000)
    parser.add_argument('--rovers', type=int, default=2)
    parser.add_argument('--drones', type=int, default=2)
    parser.add_argument('--world-size', type=int, choices=[24, 28, 32, 40, 48, 56], default=32)
    parser.add_argument('--layout', choices=['rooms', 'maze', 'cave'], default='rooms')
    parser.add_argument('--max-steps', type=int, default=400)
    parser.add_argument('--network', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--output', type=Path, default=Path('training/runs/ppo_demo_10000'))
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--fps', type=int, default=10)
    parser.add_argument('--frame-stride', type=int, default=2)
    args = parser.parse_args()
    if args.rovers < 0 or args.drones < 0 or not 1 <= args.rovers + args.drones <= 16:
        parser.error('Choose 1–16 robots in total')
    if not 1 <= args.max_steps <= 1000 or not 1 <= args.fps <= 30 or not 1 <= args.frame_stride <= 20:
        parser.error('max-steps: 1–1000, fps: 1–30, frame-stride: 1–20')
    checkpoint = args.checkpoint.resolve()
    module_root = checkpoint / 'learner_group/learner/rl_module'
    if not module_root.is_dir():
        parser.error(f'Checkpoint module directory missing: {module_root}')
    from swarm_sar.validation.seeds import load_seed_splits
    if args.seed not in load_seed_splits()['development']:
        parser.error('Use a development seed (default 10000); final test seeds remain sealed')
    if args.output.exists():
        parser.error('Output already exists; choose a fresh --output directory')
    if not args.live:
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
    import numpy as np
    import torch
    from PIL import Image
    from ray.rllib.core.rl_module.rl_module import RLModule
    from swarm_sar.learning.env import VariableSwarmRLlibEnv
    from swarm_sar.learning.inference import initial_policy_state, module_observation_size, policy_step
    from swarm_sar.learning.training import policy_mapping_fn
    from swarm_sar.viz.renderer import Renderer

    torch.set_num_threads(1)
    names = ('rover_policy', 'drone_policy')
    modules = {name: RLModule.from_checkpoint(str(module_root / name)) for name in names}
    hashes = {}
    for name, module in modules.items():
        module.to('cpu').eval()
        if module_observation_size(module) != 229:
            raise ValueError(f'{name} is not a GPU-v1 229-value policy')
        vector = torch.cat([p.detach().reshape(-1) for p in module.parameters()])
        if not torch.isfinite(vector).all():
            raise ValueError(f'Non-finite parameters: {name}')
        hashes[name] = hashlib.sha256(vector.numpy().tobytes()).hexdigest()
    expected_hashes = checkpoint / 'parameter_hashes.json'
    if expected_hashes.exists() and hashes != json.loads(expected_hashes.read_text()):
        raise ValueError('Restored parameter hashes do not match checkpoint verification')
    environment = {
        'curriculum': False, 'domain_randomization': False,
        'fixed_team_profile': {'rover': args.rovers, 'drone': args.drones},
        'final_team_profiles': [{'rover': args.rovers, 'drone': args.drones}],
        'network_enabled': args.network, 'max_steps': args.max_steps,
        'world_sizes': [args.world_size],
        'world_overrides': {'layout': args.layout, 'footprint': 'full', 'max_generation_retries': 100},
    }
    env = VariableSwarmRLlibEnv(environment)
    renderer = None
    frames = []
    stopped = False
    try:
        observations, _ = env.reset(seed=args.seed)
        renderer = Renderer(env.env.core, rgb_array=not args.live)
        pygame = renderer.pygame
        clock = pygame.time.Clock()
        states = {agent: initial_policy_state(modules[policy_mapping_fn(agent)]) for agent in env.agents}
        def capture():
            pixels = renderer.draw()
            if pixels is None:
                pixels = np.transpose(pygame.surfarray.array3d(renderer.surface), (1, 0, 2))
            frame = Image.fromarray(pixels).convert('P', palette=Image.Palette.ADAPTIVE, colors=96)
            frames.append(frame)
        capture()
        steps = 0
        print(json.dumps({'phase': 'inference', 'seed': args.seed, 'policies': hashes, 'device': 'cpu'}), flush=True)
        while env.agents:
            if args.live:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q)):
                        stopped = True
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_v:
                        renderer.toggle_vision()
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_g:
                        renderer.toggle_ground_truth()
                if stopped:
                    break
            actions = {}
            for agent, observation in observations.items():
                if agent in env.agents:
                    actions[agent], states[agent] = policy_step(modules[policy_mapping_fn(agent)], observation, None, states[agent])
            observations, _, _, _, _ = env.step(actions)
            steps += 1
            if steps % args.frame_stride == 0:
                capture()
            elif args.live:
                renderer.draw()
            if args.live:
                clock.tick(args.fps)
            if steps % 50 == 0:
                metrics = env.metrics_snapshot()
                print(json.dumps({key: metrics[key] for key in ('step', 'victims_found', 'survivors_total', 'coverage', 'collisions', 'invalid_actions')}), flush=True)
        capture()
        args.output.mkdir(parents=True)
        env.env.core.save_episode(args.output)
        frames[0].save(args.output / 'mission.gif', save_all=True, append_images=frames[1:],
                       duration=round(1000 * args.frame_stride / args.fps), loop=0, optimize=False)
        manifest = {'controller': 'saved recurrent PPO; deterministic inference, no training',
                    'checkpoint': str(checkpoint), 'checkpoint_tree_sha256': checkpoint_digest(checkpoint),
                    'policy_parameter_sha256': hashes, 'seed': args.seed, 'seed_split': 'development',
                    'environment': environment, 'metrics': env.metrics_snapshot(), 'interrupted': stopped,
                    'viewer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'frame_count': len(frames), 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                    'limits': 'Illustrative Python grid mission, not a new benchmark or browser/ROS integration.'}
        (args.output / 'demo_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        print(json.dumps({'phase': 'saved', 'output': str(args.output.resolve()), 'metrics': {key: manifest['metrics'][key] for key in ('step', 'victims_found', 'survivors_total', 'coverage', 'collisions', 'invalid_actions')}}, indent=2), flush=True)
    finally:
        if renderer:
            renderer.close()
        env.close()


if __name__ == '__main__':
    main()
