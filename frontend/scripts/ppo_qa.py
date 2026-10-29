"""Real browser-to-Python PPO checks. Start Vite :5173 and ppo_service :8765 first."""
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
from datetime import datetime, timezone
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
SHOTS = Path(tempfile.gettempdir()) / 'swarm-ppo-qa'
SHOTS.mkdir(exist_ok=True)

async def main():
  async with async_playwright() as p:
    browser=await p.chromium.launch(channel='chrome',headless=True,args=['--use-angle=metal','--ignore-gpu-blocklist'])
    page=await browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    await page.goto('http://127.0.0.1:5173/')
    await page.get_by_role('button',name='Controller settings',exact=True).click()
    await page.get_by_role('radio',name='PPO · 754k',exact=True).click()
    await page.wait_for_function("document.querySelector('.world-heading h1')?.textContent.includes('PPO Rescue Site')")
    await page.evaluate('''async()=>{const r=performance.getEntriesByType('resource');window.sim=await import(r.find(e=>e.name.includes('/src/store/simStore.ts')).name);window.remote=await import(r.find(e=>e.name.includes('/src/ppo/RemoteEngine.ts')).name);const f=await import(r.find(e=>e.name.includes('@react-three_fiber.js')).name);window.root=f._roots.get(document.querySelector('.stage canvas')).store}''')
    initial=await page.evaluate('''()=>{const s=sim.useSim.getState();return {mode:s.controllerMode,phase:s.ppoPhase,step:s.engine.step,width:s.engine.scenario.width,instance:s.engine instanceof remote.RemoteEngine,mission:s.engine.mission}}''')
    assert initial=={'mode':'ppo','phase':'ready','step':0,'width':32,'instance':True,'mission':initial['mission']},initial
    await page.get_by_role('button',name='Close panel',exact=True).click()
    # Local engine ticks must never execute while PPO owns the mission.
    await page.evaluate("()=>{sim.useSim.getState().engine.tick=()=>{throw new Error('Browser attempted PPO physics')}}")
    await page.get_by_role('button',name='Open mission panel',exact=True).click()
    assert await page.get_by_role('heading',name='Mission setup',exact=True).is_visible()
    assert await page.get_by_role('button',name='Place on map',exact=False).count()==0
    await page.get_by_role('button',name='Close panel',exact=True).click()
    await page.get_by_role('button',name='Launch mission',exact=True).click()
    await page.get_by_role('button',name='4 times speed',exact=True).click()
    await page.wait_for_function('sim.useSim.getState().engine.step>=3')
    await page.get_by_role('button',name='Pause mission',exact=True).click()
    await page.wait_for_timeout(350)
    paused=await page.evaluate('sim.useSim.getState().engine.step')
    await page.wait_for_timeout(400)
    assert await page.evaluate('sim.useSim.getState().engine.step')==paused
    backend=await (await page.request.get('http://127.0.0.1:5173/api/ppo/missions/'+initial['mission'])).json()
    frontend=await page.evaluate('''()=>{const s=sim.useSim.getState();return {grid:[...s.engine.scenario.grid.cells],robots:s.engine.robots.map(r=>[r.name,r.x,r.y,r.battery]),coverage:s.engine.coverage()}}''')
    assert frontend['grid']==backend['grid']
    assert frontend['robots']==[[r['name'],r['x'],r['y'],r['battery']] for r in backend['robots']]
    assert frontend['coverage']==backend['metrics']['coverage']
    await page.get_by_role('button',name='Resume mission',exact=True).click()
    seen=[]
    for _ in range(5):
      await page.wait_for_function("sim.useSim.getState().encounter!==null || sim.useSim.getState().status==='complete' || sim.useSim.getState().ppoPhase==='error'",timeout=30000)
      state=await page.evaluate('''()=>{const s=sim.useSim.getState();return {id:s.encounter?.id,phase:s.ppoPhase,error:s.ppoError,status:s.status,step:s.engine.step}}''')
      assert state['phase']=='ready',state
      if state['status']=='complete':break
      seen.append(state['id'])
      await page.wait_for_timeout(300)
      assert await page.evaluate('sim.useSim.getState().engine.step')==state['step']
      await page.get_by_role('dialog').get_by_role('button').click()
    await page.wait_for_function("sim.useSim.getState().status==='complete'")
    final=await page.evaluate('''()=>{const s=sim.useSim.getState();return {step:s.engine.step,found:s.engine.survivorsFound(),coverage:s.engine.coverage(),collisions:s.engine.collisions,mode:s.controllerMode}}''')
    assert final=={'step':94,'found':4,'coverage':0.9047619047619048,'collisions':0,'mode':'ppo'},final
    assert len(set(seen))==4,seen
    await page.screenshot(path=str(SHOTS/'completed.png'))
    await page.get_by_role('button',name='Start a new mission',exact=True).click()
    await page.wait_for_function("sim.useSim.getState().ppoPhase==='ready' && sim.useSim.getState().engine.step===0")
    assert await page.evaluate('sim.useSim.getState().engine.mission')!=initial['mission']
    await page.get_by_role('button',name='Launch mission',exact=True).click()
    await page.wait_for_function('sim.useSim.getState().engine.step>=2')
    await page.route('**/api/ppo/missions/*/step',lambda route:route.abort())
    await page.wait_for_function("sim.useSim.getState().ppoPhase==='error'")
    failed=await page.evaluate('''()=>{const s=sim.useSim.getState();return {step:s.engine.step,mode:s.controllerMode,status:s.status}}''')
    await page.wait_for_timeout(450)
    assert await page.evaluate('sim.useSim.getState().engine.step')==failed['step']
    assert failed['mode']=='ppo' and failed['status']=='paused',failed
    assert await page.get_by_role('button',name='Resume mission',exact=True).is_disabled()
    await page.screenshot(path=str(SHOTS/'offline.png'))
    await page.unroute('**/api/ppo/missions/*/step')
    await page.get_by_role('button',name='Reset PPO mission',exact=True).click()
    await page.wait_for_function("sim.useSim.getState().ppoPhase==='ready' && sim.useSim.getState().engine.step===0")
    await page.set_viewport_size({'width':390,'height':844})
    await page.get_by_role('button',name='Controller settings',exact=True).click()
    await page.wait_for_timeout(350)
    await page.screenshot(path=str(SHOTS/'mobile-controller.png'))
    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    await page.get_by_role('spinbutton',name='PPO seed',exact=True).fill('10001')
    await page.get_by_role('combobox',name='PPO map size',exact=True).select_option('40')
    await page.get_by_role('combobox',name='PPO layout',exact=True).select_option('maze')
    await page.get_by_role('spinbutton',name='PPO rovers',exact=True).fill('1')
    await page.get_by_role('spinbutton',name='PPO drones',exact=True).fill('1')
    await page.get_by_role('checkbox',name='PPO radio',exact=True).uncheck()
    await page.get_by_role('button',name='New PPO mission',exact=True).click()
    await page.wait_for_function("sim.useSim.getState().ppoPhase==='ready' && sim.useSim.getState().engine.scenario.width===40")
    profile=await page.evaluate("()=>{const s=sim.useSim.getState();return {seed:s.engine.scenario.seed,robots:s.engine.robots.length,radio:s.engine.network.enabled}}")
    assert profile=={'seed':10001,'robots':2,'radio':False},profile
    await page.get_by_role('button',name='Controller settings',exact=True).click()
    await page.get_by_role('radio',name='Heuristic',exact=True).click()
    await page.get_by_role('button',name='Close panel',exact=True).click()
    assert await page.evaluate("sim.useSim.getState().controllerMode==='heuristic' && sim.useSim.getState().status==='ready'")
    await page.get_by_role('button',name='Launch mission',exact=True).click()
    await page.wait_for_function('sim.useSim.getState().engine.step>0')
    assert not errors,errors
    report={'generatedAt':datetime.now(timezone.utc).isoformat(),'browserVersion':browser.version,'controller':'actual saved recurrent PPO via local Python service','pythonServiceSha256':hashlib.sha256((ROOT/'tools/ppo_service.py').read_bytes()).hexdigest(),'initial':initial,'final':final,'discoveryIds':seen,'gridPositionsBatteryAndCoverageMatchPython':True,'pauseAndDiscoveryStopAdvancement':True,'resetStartsFreshPythonMission':True,'connectionLossPausesWithoutHeuristicFallback':True,'recoveryResetWorks':True,'heuristicModeStillRuns':True,'mobileNoOverflow':True,'newMazeSeedTeamAndRadioOptionsWork':True,'errors':errors,'sourceHashes':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'frontend/src').rglob('*')) if f.suffix in ('.ts','.tsx','.css')}}
    (ROOT/'docs/browser_ppo_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='sourceHashes'},indent=2))
    await browser.close()

asyncio.run(main())
