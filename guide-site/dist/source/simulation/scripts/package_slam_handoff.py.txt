"""Package only the reviewed SLAM changes; verify reconstruction on a fixed base.

No checkout, commit, push, overwrite or ROS installation is performed.
"""
from pathlib import Path
import argparse
import hashlib
import gzip
import io
import json
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_BASE='83cd96ce7a5651ee77f5816a7ab47844bc0cbf7a'
TRACKED=[
    'frontend/src/components/TopBar.tsx','frontend/src/main.tsx',
    'frontend/src/app/App.tsx','frontend/src/components/ControllerControls.tsx',
    'frontend/src/components/Icon.tsx','frontend/src/components/LeftPanel.tsx',
    'frontend/src/components/SceneHud.tsx','frontend/src/ppo/PPOBridge.tsx',
    'frontend/src/store/simStore.ts','frontend/src/tests/ppo.test.ts','backend/ppo_service.py',
    'simulation/ros2_ws/src/swarm_sar_control/package.xml','simulation/ros2_ws/src/swarm_sar_control/setup.py',
    *['simulation/ros2_ws/src/swarm_sar_control/swarm_sar_control/'+name+'.py' for name in
      ('decentralized_agent','disaster_scene','peer_network_bridge','survivor_oracle','waypoint_demo')],
    'simulation/ros2_ws/src/swarm_sar_description/urdf/rover.urdf.xacro',
    'simulation/ros2_ws/src/swarm_sar_gazebo/package.xml','tests/ros2/test_physical_models.py',
]
NEW=[
    'docs/guides/slam_integration.md','docs/guides/LINUX_SLAM_VALIDATION_PROMPT.md',
    'docs/audits/slam_local_validation.md','docs/audits/ros_branch_pr_audit.md',
    'frontend/src/tests/rosTransport.test.ts','frontend/tools/validate_observatory_ui.py',
    'frontend/src/ros/transport.ts',
    *[str(path.relative_to(ROOT)) for path in sorted((ROOT/'frontend/src/observatory').glob('*')) if path.is_file()],
    'frontend/src/styles/world-polish.css','frontend/src/tests/observatoryTelemetry.test.ts',
    *['simulation/ros2_ws/src/swarm_sar_control/swarm_sar_control/'+name+'.py' for name in ('slam_agent','slam_support')],
    'simulation/ros2_ws/src/swarm_sar_gazebo/launch/slam_demo.launch.py',
    *['simulation/ros2_ws/src/swarm_sar_gazebo/config/'+name for name in ('slam_demo.rviz','slam_rover.yaml')],
    'simulation/ros2_ws/tools/slam_runtime_probe.py','tests/ros2/test_slam_support.py',
    'simulation/scripts/package_slam_handoff.py',
]

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def digest(data):return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-ref',default=DEFAULT_BASE,help='Pre-SLAM commit; retained after the integration is committed')
    args=parser.parse_args()
    baseline=git('rev-parse',args.base_ref+'^{commit}').decode().strip()
    patch=git('diff','--binary',baseline,'--',*TRACKED)
    files={'tracked.patch':patch,**{'new/'+name:(ROOT/name).read_bytes() for name in NEW}}
    for source,target in [('artifacts/slam_local_python_tests.txt','evidence/python_tests.txt'),
                          ('artifacts/observatory_redesign/validation.json','evidence/synthetic_rosbridge_ui_contract.json'),
                          ('artifacts/observatory_redesign/ros-disconnected.png','evidence/disconnected_real_ui.png')]:
        files[target]=(ROOT/source).read_bytes()
    manifest=dict(base_commit=baseline,
        instruction='Stage and review; preserve Linux PPO source/entry points. Never blindly overwrite a different or dirty checkout.',
        tracked_result_sha256={name:digest((ROOT/name).read_bytes()) for name in TRACKED},
        files={name:dict(bytes=len(data),sha256=digest(data)) for name,data in files.items()})
    # Reconstruct the patch on an isolated copy of the actual baseline files.
    with tempfile.TemporaryDirectory(prefix='swarm_slam_patch_check_') as directory:
        staging=Path(directory)
        archive=git('archive',baseline,*TRACKED)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(staging,filter='data')
        patchfile=staging/'tracked.patch'; patchfile.write_bytes(patch)
        subprocess.run(['git','apply','--check',str(patchfile)],cwd=staging,check=True)
        subprocess.run(['git','apply',str(patchfile)],cwd=staging,check=True)
        for name,expected in manifest['tracked_result_sha256'].items():
            assert digest((staging/name).read_bytes())==expected,name
    files['MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    output=ROOT/'artifacts/slam_linux_handoff.tar.gz'; output.parent.mkdir(parents=True,exist_ok=True)
    # Stable gzip metadata keeps rebuilding the same committed inputs byte-identical.
    with output.open('wb') as target:
        with gzip.GzipFile(filename='',mode='wb',fileobj=target,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w') as tar:
                for name,data in files.items():
                    info=tarfile.TarInfo(name); info.size=len(data); info.mode=0o644
                    tar.addfile(info,io.BytesIO(data))
    with tarfile.open(output) as tar:
        for name,expected in manifest['files'].items():
            assert digest(tar.extractfile(name).read())==expected['sha256'],name
    report=dict(archive=str(output.relative_to(ROOT)),sha256=digest(output.read_bytes()),
                bytes=output.stat().st_size,baseline_patch_reconstruction='passed',payload_checksums='passed',
                new_files=len(NEW),tracked_files=len(TRACKED),base_commit=manifest['base_commit'])
    (ROOT/'artifacts/slam_handoff_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
