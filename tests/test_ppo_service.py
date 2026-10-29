"""Real saved-policy integration: no training, fabricated actions or test seeds."""
import json
from pathlib import Path
import tarfile

import pytest

from tools.ppo_service import Service, options

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def service(tmp_path_factory):
    root = tmp_path_factory.mktemp('ppo-service')
    archive = ROOT / 'artifacts/trained/ppo_754k/swarm-754k-handoff.tar.gz'
    with tarfile.open(archive) as tar:
        tar.extractall(root, filter='data')
    app = Service(root / 'results/gpu_continue_1m/checkpoints/step_000000753664')
    yield app
    for mission in app.sessions.values():
        mission.env.close()


def test_rejects_truth_commands_final_seeds_and_invalid_options():
    for value in [None, [], {'seed': 20000}, {'seed': True}, {'rovers': 10, 'drones': 10},
                  {'size': 9999}, {'layout': 'unknown'}, {'network': 1}, {'victims': [[3, 4]]}]:
        with pytest.raises(ValueError):
            options(value)


def test_real_checkpoint_mission_matches_recorded_review_and_duplicate_steps(service):
    initial = service.request('POST', '/api/ppo/missions', {})
    url = '/api/ppo/missions/' + initial['mission']
    assert initial['step'] == 0
    assert initial['metrics']['victims_found'] == 0
    assert initial['provenance']['observationSize'] == 229
    assert service.request('GET', url) == initial
    snapshot = service.request('POST', url + '/step', {'expectedStep': 0})
    assert snapshot['step'] == 1
    assert service.request('POST', url + '/step', {'expectedStep': 0}) == snapshot
    with pytest.raises(ValueError):
        service.request('POST', url + '/step', {'expectedStep': 5})
    with pytest.raises(ValueError):
        service.request('POST', url + '/step', {'expectedStep': 1, 'actions': {'rover_0': 6}})
    while not snapshot['done']:
        snapshot = service.request('POST', url + '/step', {'expectedStep': snapshot['step']})
        # JSON serialization itself must succeed at every step, including peers.
        json.dumps(snapshot, allow_nan=False)
    review = json.loads((ROOT / 'artifacts/trained/ppo_754k/ppo_754k_review.json').read_text())
    expected = next(row for row in review['cohorts']['nominal_2r2d']['episodes'] if row['seed'] == 10000)
    assert snapshot['step'] == expected['steps'] == 94
    assert snapshot['metrics']['victims_found'] == expected['survivors_found'] == 4
    assert snapshot['metrics']['coverage'] == expected['coverage']
    assert snapshot['metrics']['invalid_actions'] == 0
    assert snapshot['metrics']['collisions'] == 0
    assert snapshot['doneReason'] == 'all_found'
    assert all(v['foundBy'] in {r['name'] for r in snapshot['robots']} for v in snapshot['victims'])
    assert snapshot['network']['messages_delivered'] > 0
    service.request('DELETE', url)


def test_sessions_are_isolated_and_reset_reproduces_start(service):
    first = service.request('POST', '/api/ppo/missions', {})
    second = service.request('POST', '/api/ppo/missions', {})
    a, b = '/api/ppo/missions/' + first['mission'], '/api/ppo/missions/' + second['mission']
    assert first['mission'] != second['mission']
    one = service.request('POST', a + '/step', {'expectedStep': 0})
    assert service.request('GET', b)['step'] == 0
    two = service.request('POST', b + '/step', {'expectedStep': 0})
    for key in ('robots', 'victims', 'metrics', 'grid', 'peers'):
        assert one[key] == two[key]
    service.request('DELETE', a)
    service.request('DELETE', b)
    with pytest.raises(KeyError):
        service.request('GET', a)


def test_browser_reconnect_releases_previous_mission(service):
    first = service.request('POST', '/api/ppo/missions', {'clientKey': 'browser-client-12345'})
    second = service.request('POST', '/api/ppo/missions', {'clientKey': 'browser-client-12345'})
    assert first['mission'] not in service.sessions
    assert second['mission'] in service.sessions
    service.request('DELETE', '/api/ppo/missions/' + second['mission'])


def test_http_rejects_cross_site_writes_and_bad_json(service):
    import threading
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    from http.server import ThreadingHTTPServer
    from tools.ppo_service import Handler
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.service = service
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/api/ppo/missions'
    try:
        for headers, body, status in [
            ({'Content-Type': 'application/json', 'Origin': 'https://unrelated.example'}, b'{}', 403),
            ({'Content-Type': 'text/plain'}, b'{}', 415),
            ({'Content-Type': 'application/json'}, b'{bad', 400),
        ]:
            with pytest.raises(HTTPError) as error:
                urlopen(Request(base, data=body, headers=headers, method='POST'))
            assert error.value.code == status
        with urlopen(base.rsplit('/missions', 1)[0] + '/health') as response:
            assert json.load(response)['ready'] is True
    finally:
        server.shutdown()
        server.server_close()


def test_fresh_checkout_extracts_verified_default_archive(tmp_path, monkeypatch):
    import shutil
    import tools.ppo_service as module
    bundle = tmp_path / 'artifacts/trained/ppo_754k'
    bundle.mkdir(parents=True)
    original = ROOT / 'artifacts/trained/ppo_754k'
    for name in ('swarm-754k-handoff.tar.gz', 'swarm-754k-handoff.sha256'):
        shutil.copyfile(original / name, bundle / name)
    checkpoint = tmp_path / 'results/ppo_754k_handoff/results/gpu_continue_1m/checkpoints/step_000000753664'
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'DEFAULT_CHECKPOINT', checkpoint)
    module.prepare_checkpoint(checkpoint)
    expected = json.loads((original / 'ppo_754k_review.json').read_text())['checkpoint_provenance']['tree_sha256']
    assert module.digest_tree(checkpoint) == expected
