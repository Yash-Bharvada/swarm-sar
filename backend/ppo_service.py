"""Local HTTP mission service: saved GPU-v1 policies own every simulated step.

Run from the repo root: .venv/bin/python backend/ppo_service.py
The browser uses Vite's /api/ppo proxy. No training or Ray cluster is started.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path, PurePosixPath
import secrets
import re
import tarfile
import threading
import time
from urllib.parse import urlsplit
import zlib

import numpy as np
import torch
from ray.rllib.core.rl_module.rl_module import RLModule
from swarm_sar.learning.env import VariableSwarmRLlibEnv
from swarm_sar.learning.inference import initial_policy_state, module_observation_size, policy_step
from swarm_sar.learning.training import policy_mapping_fn
from swarm_sar.validation.seeds import load_seed_splits
from swarm_sar.sensing.vision import bresenham_line

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT = ROOT / 'training/runs/ppo_754k_handoff/results/gpu_continue_1m/checkpoints/step_000000753664'


def digest_tree(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def prepare_checkpoint(checkpoint):
    if checkpoint != DEFAULT_CHECKPOINT or checkpoint.exists():
        return
    bundle = ROOT / 'models/ppo_754k'
    archive = bundle / 'swarm-754k-handoff.tar.gz'
    expected = (bundle / 'swarm-754k-handoff.sha256').read_text().split()[0]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise ValueError('Checkpoint archive checksum failed')
    target = ROOT / 'training/runs/ppo_754k_handoff'
    if target.exists():
        raise ValueError('Incomplete extraction exists; preserve it and choose a fresh checkpoint path')
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe archive member')
        target.mkdir(parents=True)
        tar.extractall(target, filter='data')


def integer(data, key, default, low, high):
    if not isinstance(data, dict):
        raise ValueError('JSON object required')
    value = data.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{key} must be an integer from {low} to {high}')
    return value


def options(data):
    if not isinstance(data, dict) or set(data) - {'seed', 'rovers', 'drones', 'size', 'layout', 'network', 'batteryLimited', 'timeLimit'}:
        raise ValueError('Unknown mission options')
    seed = integer(data, 'seed', 10000, 10000, 10099)
    if seed not in load_seed_splits()['development']:
        raise ValueError('Only development seeds are permitted')
    rovers = integer(data, 'rovers', 2, 0, 10)
    drones = integer(data, 'drones', 2, 0, 10)
    size = integer(data, 'size', 32, 24, 56)
    if not 1 <= rovers + drones <= 10 or size not in (24, 28, 32, 40, 48, 56):
        raise ValueError('Choose 1–10 robots and a supported map size')
    layout, network = data.get('layout', 'rooms'), data.get('network', True)
    if layout not in ('rooms', 'maze', 'cave') or type(network) is not bool:
        raise ValueError('Invalid layout or radio setting')
    battery_limited = data.get('batteryLimited', True)
    if type(battery_limited) is not bool:
        raise ValueError('batteryLimited must be a boolean')
    duration = data.get('timeLimit', 400)
    if duration is not None and (type(duration) is not int or not 1 <= duration <= 86400):
        raise ValueError('Choose a valid mission duration')
    return dict(seed=seed, rovers=rovers, drones=drones, size=size, layout=layout, network=network,
                batteryLimited=battery_limited, **({'timeLimit': duration} if 'timeLimit' in data else {}))


class Mission:
    def __init__(self, config, modules, provenance):
        self.id = secrets.token_urlsafe(24)
        self.config, self.modules, self.provenance = config, modules, provenance
        self.touched = time.monotonic()
        self.max_steps = config.get('timeLimit', 400)
        if self.max_steps is None:
            self.max_steps = (1 << 53) - 1  # JSON-safe, effectively unbounded horizon
        profile = {'rover': config['rovers'], 'drone': config['drones']}
        self.env = VariableSwarmRLlibEnv({
            'curriculum': False, 'domain_randomization': False, 'fixed_team_profile': profile,
            'final_team_profiles': [profile], 'world_sizes': [config['size']],
            'network_enabled': config['network'], 'max_steps': self.max_steps,
            'world_overrides': {'layout': config['layout'], 'footprint': 'full', 'max_generation_retries': 100},
        })
        # Mission-local override: keep the audited training sources and the
        # 229-value observation contract intact. Zero costs keep battery full
        # without infinities, refilling between ticks, or reviving dead agents.
        if not config.get('batteryLimited', True):
            for robot in self.env.base_robots.values():
                robot.update(move_cost=0.0, rubble_cost=0.0, idle_cost=0.0)
        try:
            self.observations, _ = self.env.reset(seed=config['seed'])
            self.states = {agent: initial_policy_state(modules[policy_mapping_fn(agent)]) for agent in self.env.agents}
            self.actions = {}
            self.last = self.snapshot()
        except Exception:
            self.env.close()
            raise

    def step(self, expected):
        current = self.env.env.core.step_count
        # A retry after a lost response returns the same state, never an extra tick.
        if expected == current - 1:
            return self.last
        if expected != current:
            raise ValueError('Step conflict: reset/reconnect rather than skipping state')
        if self.env.agents:
            actions = {}
            for agent, observation in self.observations.items():
                if agent in self.env.agents:
                    actions[agent], self.states[agent] = policy_step(
                        self.modules[policy_mapping_fn(agent)], observation, None, self.states[agent])
            self.observations, _, _, _, _ = self.env.step(actions)
            self.actions = actions
            self.last = self.snapshot()
        return self.last

    def snapshot(self):
        env, core = self.env.env, self.env.env.core
        metrics = self.env.metrics_snapshot()
        net = env.network
        robots = []
        for r in core.robots:
            c = core.robot_configs[r.type]
            robots.append({**r.as_state(), 'name': r.name, 'maxBattery': c['battery'],
                'belief': r.belief.ravel().tolist(), 'visited': r.visited.ravel().astype(int).tolist(),
                'thermal': r.thermal.tolist(), 'acoustic': float(r.acoustic[0]),
                'distanceTravelled': r.distance_travelled, 'lastAction': r.last_action,
                'collided': r.collided, 'action': self.actions.get(r.name),
                'goal': env._active_goals.get(r.name),
                'radii': {k: c[k] for k in ('vision_radius', 'thermal_radius', 'acoustic_radius', 'comm_radius')},
            })
        victims = [{**v, 'foundBy': next((r.name for r in core.robots if r.id == v.get('found_by')), None)} for v in core.victims]
        links, peers, packets = [], {}, []
        if net:
            for i, a in enumerate(core.robots):
                for b in core.robots[i+1:]:
                    if not a.alive or not b.alive:
                        continue
                    linked, reason = net._radio_link(a, b, core.robot_configs, core.grid)
                    if net._partitioned(a.name, b.name, core.step_count):
                        linked, reason = False, 'partition'
                    links.append({'a': a.name, 'b': b.name, 'health': 'healthy' if linked else 'down',
                                  'reason': reason, 'step': core.step_count,
                                  'distance': float(np.hypot(a.x-b.x, a.y-b.y)), 'walls': int(sum(core.grid[y, x] == 1 for x, y in bresenham_line(a.position, b.position)[1:-1]))})
            peers = {r.name: [{**asdict(m), 'estimated_bytes': m.estimated_bytes} for m in net.peer_messages(r.name, core.step_count)] for r in core.robots}
            for item in net.scheduled:
                m = item.message
                packets.append({'id': zlib.crc32(f'{m.sender_id}:{m.seq}:{item.recipient}'.encode()),
                    'from': m.sender_id, 'to': item.recipient, 'sentStep': m.sent_step,
                    'arriveStep': item.deliver_step, 'outcome': 'in-flight',
                    'mapCells': len(m.payload.get('map_cells', []))})
        found = int(metrics['victims_found'])
        done = not self.env.agents
        reason = ('all_found' if found == len(core.victims) else 'all_depleted' if not any(r.alive for r in core.robots) else 'timeout') if done else None
        return {'protocol': 1, 'mission': self.id, 'controller': 'ppo', 'provenance': self.provenance,
            'options': self.config, 'step': core.step_count, 'done': done, 'doneReason': reason,
            'grid': core.grid.ravel().tolist(), 'width': int(core.grid.shape[1]), 'height': int(core.grid.shape[0]),
            'spawn': list(core.world_config['spawn_origin']), 'spawnSize': int(core.world_config['spawn_size']),
            'victims': victims, 'robots': robots, 'links': links, 'peers': peers, 'packets': packets,
            'transport': {'packetLoss': net.packet_loss if net else 0, 'delay': [net.delay_min, net.delay_max] if net else [1, 2], 'ttl': net.ttl if net else 8},
            'network': env.network_metrics(),
            'metrics': {k: metrics[k] for k in ('coverage', 'collisions', 'invalid_actions', 'victims_found', 'survivors_total')},
            'maxSteps': self.max_steps}


class Service:
    def __init__(self, checkpoint):
        torch.set_num_threads(1)
        prepare_checkpoint(checkpoint)
        report = json.loads((ROOT / 'models/ppo_754k/ppo_754k_review.json').read_text())
        digest = digest_tree(checkpoint)
        if digest != report['checkpoint_provenance']['tree_sha256']:
            raise ValueError('Checkpoint does not match the selected 754k evaluation provenance')
        base = checkpoint / 'learner_group/learner/rl_module'
        self.modules = {name: RLModule.from_checkpoint(str(base / name)).to('cpu').eval() for name in ('rover_policy', 'drone_policy')}
        hashes = {}
        for name, module in self.modules.items():
            if module_observation_size(module) != 229:
                raise ValueError('Wrong policy observation contract')
            vector = torch.cat([p.detach().reshape(-1) for p in module.parameters()])
            if not torch.isfinite(vector).all():
                raise ValueError('Non-finite model parameters')
            hashes[name] = hashlib.sha256(vector.numpy().tobytes()).hexdigest()
        if hashes != json.loads((checkpoint / 'parameter_hashes.json').read_text()):
            raise ValueError('Restored policy parameter verification failed')
        self.provenance = {'checkpointStep': 753664, 'checkpointTreeSha256': digest, 'policyHashes': hashes,
                           'observationVersion': 'gpu-v1', 'observationSize': 229, 'device': 'cpu', 'finalSeedsUsed': False}
        self.sessions = {}
        self.lock = threading.RLock()

    def request(self, method, path, data=None):
        with self.lock:
            now = time.monotonic()
            for key, mission in list(self.sessions.items()):
                if now - mission.touched > 1800:
                    mission.env.close()
                    del self.sessions[key]
            if method == 'GET' and path == '/api/ppo/health':
                return {'ready': True, 'controller': 'ppo', 'provenance': self.provenance}
            if method == 'POST' and path == '/api/ppo/missions':
                if not isinstance(data, dict):
                    raise ValueError('JSON object required')
                client_key = data.get('clientKey')
                if client_key is not None and (not isinstance(client_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', client_key)):
                    raise ValueError('Invalid browser client key')
                config = options({key: value for key, value in data.items() if key != 'clientKey'})
                if client_key:
                    for key, old in list(self.sessions.items()):
                        if getattr(old, 'client_key', None) == client_key:
                            old.env.close()
                            del self.sessions[key]
                if len(self.sessions) >= 4:
                    raise ValueError('Four missions already active; close or reset an old mission')
                mission = Mission(config, self.modules, self.provenance)
                mission.client_key = client_key
                self.sessions[mission.id] = mission
                return mission.last
            parts = path.split('/')
            if len(parts) not in (5, 6) or parts[:4] != ['', 'api', 'ppo', 'missions']:
                raise KeyError('Unknown endpoint')
            mission = self.sessions[parts[4]]
            mission.touched = now
            if method == 'DELETE' and len(parts) == 5:
                mission.env.close()
                del self.sessions[mission.id]
                return {'closed': True}
            if method == 'GET' and len(parts) == 5:
                return mission.last
            if method == 'POST' and len(parts) == 6 and parts[5] == 'step':
                if not isinstance(data, dict) or set(data) != {'expectedStep'}:
                    raise ValueError('Only an expected step counter is accepted')
                expected = integer(data, 'expectedStep', -1, 0, mission.max_steps)
                return mission.step(expected)
            raise KeyError('Unknown endpoint')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def send_json(self, code, payload):
        body = json.dumps(payload, allow_nan=False, separators=(',', ':')).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def handle_request(self, method):
        # Local-only service; JSON writes and origin/host checks also block
        # cross-site form submissions and DNS-rebinding browser requests.
        try:
            host = urlsplit('http://' + self.headers.get('Host', '')).hostname
            origin = self.headers.get('Origin')
            if host not in ('localhost', '127.0.0.1') or (origin and origin not in ('http://localhost:5173', 'http://127.0.0.1:5173')):
                return self.send_json(403, {'error': 'Local frontend origin required'})
            data = None
            if method == 'POST':
                if self.headers.get_content_type() != 'application/json':
                    return self.send_json(415, {'error': 'JSON required'})
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    return self.send_json(413, {'error': 'Invalid request size'})
                data = json.loads(self.rfile.read(length))
            self.send_json(200, self.server.service.request(method, urlsplit(self.path).path, data))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.send_json(400, {'error': str(error)})
        except KeyError:
            self.send_json(404, {'error': 'Mission or endpoint not found; create a new mission'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            print(f'Mission error: {error}', flush=True)
            self.send_json(500, {'error': 'PPO service failed; pause and reset the mission'})

    def do_GET(self):
        self.handle_request('GET')

    def do_POST(self):
        self.handle_request('POST')

    def do_DELETE(self):
        self.handle_request('DELETE')

    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    service = Service(args.checkpoint.resolve())
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.daemon_threads = True
    server.service = service
    print(f'PPO service ready at http://127.0.0.1:{args.port}; verified checkpoint 753664', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        for mission in service.sessions.values():
            mission.env.close()


if __name__ == '__main__':
    main()
