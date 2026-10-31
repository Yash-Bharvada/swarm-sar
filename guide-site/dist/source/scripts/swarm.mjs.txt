#!/usr/bin/env node
/** Start the local workstation services. ROS/Gazebo remain on the sourced Linux host. */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import net from 'node:net';
import readline from 'node:readline';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const python = resolve(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const args = process.argv.slice(2);
if (args.includes('--help')) {
  console.log('npm run swarm [-- --check]\nStarts/reuses the 3D frontend (5173), PPO backend (8765) and audiobook (8088).\n--check validates prerequisites and reports service health without starting anything.\nCtrl+C stops only processes started by this command. ROS/Gazebo must run on Linux.');
  process.exit(0);
}
if (args.some(arg => arg !== '--check')) { console.error('Unknown option. Run npm run swarm -- --help.'); process.exit(1); }
const children = new Set();
let stopping = false;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill('SIGTERM');
  const force = setTimeout(() => { for (const child of children) child.kill('SIGKILL'); process.exit(code); }, 3000);
  Promise.all([...children].map(child => child.exitCode !== null ? Promise.resolve() : new Promise(resolve => child.once('exit', resolve))))
    .then(() => { clearTimeout(force); process.exit(code); });
}
process.once('SIGINT', () => stop());
process.once('SIGTERM', () => stop());
async function occupied(port) {
  return new Promise(resolve => {
    const socket = net.connect({ host: '127.0.0.1', port });
    socket.setTimeout(700);
    const finish = result => { socket.destroy(); resolve(result); };
    socket.once('connect', () => finish(true)); socket.once('error', () => finish(false)); socket.once('timeout', () => finish(false));
  });
}
async function healthy(service) {
  try {
    const response = await fetch(service.url, { signal: AbortSignal.timeout(1800) });
    if (!response.ok) return false;
    if (service.name === 'PPO') { const value = await response.json(); return value.ready === true && value.controller === 'ppo'; }
    return service.pattern.test(await response.text());
  } catch { return false; }
}
function launch(service) {
  const child = spawn(service.command, service.args, { cwd: service.cwd || root, env: { ...process.env, PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
  children.add(child);
  for (const stream of [child.stdout, child.stderr]) readline.createInterface({ input: stream }).on('line', line => console.log(`[${service.name}] ${line}`));
  child.once('error', error => { console.error(`[${service.name}] ${error.message}`); stop(1); });
  child.once('exit', (code, signal) => {
    children.delete(child);
    if (!stopping) { console.error(`[${service.name}] stopped (${signal || code}). Stopping this launch.`); stop(1); }
  });
}
try {
  if (!existsSync(python)) throw new Error('Python environment missing. First run: python3 -m venv .venv\nThen: .venv/bin/python -m pip install -e .');
  if (!existsSync(resolve(root, 'frontend/node_modules/vite/bin/vite.js'))) throw new Error('Frontend dependencies missing. First run: npm --prefix frontend ci');
  const check = spawnSync(python, ['-c', "import sys,importlib.util; assert sys.version_info >= (3,12), 'Python 3.12+ required'; missing=[x for x in ['torch','ray','swarm_sar','numpy'] if importlib.util.find_spec(x) is None]; assert not missing, 'Missing packages: '+', '.join(missing)"], { cwd: root, encoding: 'utf8' });
  if (check.status !== 0) throw new Error((check.stderr || check.error?.message || 'Python prerequisite check failed') + '\nInstall dependencies: .venv/bin/python -m pip install -e .');
  const services = [
    { name: 'PPO', port: 8765, url: 'http://127.0.0.1:8765/api/ppo/health', command: python, args: ['-m', 'backend.ppo_service'] },
    { name: 'Frontend', port: 5173, url: 'http://127.0.0.1:5173/', pattern: /Swarm — Rescue Simulation/, command: process.execPath, args: [resolve(root, 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5173', '--strictPort'], cwd: resolve(root, 'frontend') },
    { name: 'Audiobook', port: 8088, url: 'http://127.0.0.1:8088/', pattern: /SWARM SAR — The Fieldbook/, command: python, args: ['guide-site/scripts/serve.py'] },
  ];
  console.log('\nSWARM SAR · local workspace\n');
  // Inspect every port before starting any process; a different application is never replaced.
  for (const service of services) {
    service.reuse = await healthy(service);
    if (!service.reuse && await occupied(service.port)) throw new Error(`Port ${service.port} is occupied by an unhealthy or different service. Inspect it before retrying.`);
    console.log(`${service.name}: ${service.reuse ? 'already healthy' : 'not running'}`);
  }
  if (args.includes('--check')) { console.log('\nPrerequisites passed.'); process.exit(0); }
  for (const service of services) if (!service.reuse) launch(service);
  const deadline = Date.now() + 120000;
  let lastNotice = 0;
  while (!(await Promise.all(services.map(healthy))).every(Boolean)) {
    if (Date.now() > deadline) throw new Error('Startup timed out. Review the service output above.');
    if (Date.now() - lastNotice > 10000) { console.log('Waiting for services and verified PPO checkpoint…'); lastNotice = Date.now(); }
    await delay(600);
  }
  console.log('\nReady:\n  Simulator   http://127.0.0.1:5173/\n  Observatory http://127.0.0.1:5173/?mode=observatory\n  ROS view    http://127.0.0.1:5173/?mode=ros\n  Audiobook   http://127.0.0.1:8088/\n  PPO health  http://127.0.0.1:8765/api/ppo/health\n\nROS/Gazebo and rosbridge run separately on the Linux ROS host.\nCtrl+C stops services started here; existing servers remain running.\n');
  const monitor = setInterval(async () => {
    if (stopping) return;
    const states = await Promise.all(services.map(healthy));
    if (states.some(value => !value)) console.error('Service health changed. Review the local service terminals.');
  }, 15000);
  monitor.unref();
  if (children.size === 0) { console.log('All services were already running.'); process.exit(0); }
} catch (error) { console.error(`\n${error.message}`); stop(1); }
