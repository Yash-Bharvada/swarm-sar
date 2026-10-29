"""Capture actual browser renders for documentation (no synthetic image content).

Run from the repository root after starting Vite on :5173 and the PPO service
on :8765. Optional capture dependencies: playwright and Pillow.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time

from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = """() => { const s=sim.useSim.getState(), e=s.engine; return {
 controller:s.controllerMode, phase:s.ppoPhase, status:s.status, seed:e.scenario.seed,
 preset:s.settings.preset, width:e.scenario.width, height:e.scenario.height,
 robots:e.robots.map(r=>({name:r.name,type:r.type,x:r.x,y:r.y,battery:r.battery})),
 step:e.step, found:e.survivorsFound(), total:e.scenario.victims.length,
 coverage:e.coverage(), collisions:e.collisions, error:s.ppoError,
 batteryLimited:s.settings.batteryLimited, encounter:s.encounter?.id??null
}; }"""

async def capture(url: str, output: Path):
 output.mkdir(parents=True,exist_ok=True)
 records=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--use-angle=metal','--ignore-gpu-blocklist'])
  page=await browser.new_page(viewport={'width':1600,'height':1000},device_scale_factor=1)
  errors=[]
  page.on('pageerror',lambda error: errors.append(str(error)))
  await page.goto(url,wait_until='domcontentloaded')
  await page.locator('canvas').first.wait_for(state='visible',timeout=60000)
  await page.evaluate("""async()=>{window.sim=await import('/src/store/simStore.ts')}""")
  await page.wait_for_timeout(2000)

  async def snapshot(name,description):
   await page.wait_for_timeout(500)
   path=output/name
   await page.screenshot(path=str(path))
   record={'file':name,'description':description,'captured_utc':datetime.now(timezone.utc).isoformat(),'state':await page.evaluate(SNAPSHOT),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
   records.append(record)
   print(json.dumps({'captured':name,'state':record['state']}),flush=True)

  async def prepare(preset,seed,rovers,drones):
   await page.evaluate("""({preset,seed,rovers,drones})=>{const s=sim.useSim.getState();s.reset();s.setSetting('preset',preset);s.setSetting('seed',seed);s.setSetting('rovers',rovers);s.setSetting('drones',drones);s.setSetting('speed',2);s.moveCamera('isometric')}""",{'preset':preset,'seed':seed,'rovers':rovers,'drones':drones})
   await page.wait_for_timeout(700)

  await prepare('office',7,2,2)
  await snapshot('office-overview.png','Live browser UI; office seed 7, two rovers and two drones, before launch.')
  await page.get_by_role('button',name='Launch mission',exact=True).click()
  await page.wait_for_function('sim.useSim.getState().engine.step>=12 || sim.useSim.getState().encounter!==null')
  if await page.evaluate('sim.useSim.getState().encounter!==null'):
   await page.evaluate('sim.useSim.getState().continueExploration()')
  await page.evaluate('sim.useSim.getState().pause()')
  await page.get_by_role('button',name='Open fleet panel',exact=True).click()
  await snapshot('office-fleet.png','Actual paused browser mission with live fleet telemetry.')
  await page.get_by_role('button',name='Close panel',exact=True).click()

  await prepare('mine',17,1,3)
  await page.evaluate('sim.useSim.getState().launch()')
  await page.wait_for_function('sim.useSim.getState().engine.step>=10 || sim.useSim.getState().encounter!==null')
  await page.evaluate('sim.useSim.getState().pause()')
  await snapshot('mine-team.png','Live browser mine seed 17; one rover and three drones.')

  await prepare('apartment',23,3,1)
  await page.evaluate('sim.useSim.getState().launch()')
  await page.wait_for_function('sim.useSim.getState().engine.step>=10 || sim.useSim.getState().encounter!==null')
  await page.evaluate('sim.useSim.getState().pause()')
  if await page.evaluate('sim.useSim.getState().encounter!==null'):
   await page.evaluate('sim.useSim.getState().continueExploration();sim.useSim.getState().pause()')
  await snapshot('apartment-team.png','Live browser apartment seed 23; three rovers and one drone.')

  # Recorded real-time browser frames. Only GIF encoding/quantization is applied.
  await page.set_viewport_size({'width':1280,'height':800})
  await prepare('office',7,2,2)
  await page.evaluate('sim.useSim.getState().setSetting("speed",4);sim.useSim.getState().launch()')
  frames=[]; states=[]; timestamps=[]; started=time.monotonic()
  for _ in range(42):
   if await page.evaluate('sim.useSim.getState().encounter!==null'):
    await page.evaluate('sim.useSim.getState().continueExploration()')
   frames.append(Image.open(BytesIO(await page.screenshot())).convert('RGB').resize((960,600),Image.Resampling.LANCZOS).quantize(colors=96,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE))
   states.append(await page.evaluate(SNAPSHOT)); timestamps.append(time.monotonic()-started)
   await page.wait_for_timeout(180)
  durations=[max(100,round((b-a)*1000/10)*10) for a,b in zip(timestamps,timestamps[1:])]+[800]
  gif=output/'mission-live.gif'
  frames[0].save(gif,save_all=True,append_images=frames[1:],duration=durations,loop=0,optimize=True)
  records.append({'file':gif.name,'description':'Chronological real browser frames at 4x playback; discovery dialogs continued through the normal app action. Downscaled and palette-encoded as GIF for documentation. No scene content generated or retouched.','frames':len(frames),'frame_times_seconds':timestamps,'frame_states':states,'sha256':hashlib.sha256(gif.read_bytes()).hexdigest()})
  print('Captured live GIF',flush=True)

  await page.set_viewport_size({'width':1600,'height':1000})
  await page.get_by_role('button',name='Open mission panel',exact=True).click()
  await page.get_by_role('radio',name='PPO',exact=True).click()
  await page.wait_for_function("sim.useSim.getState().ppoPhase==='ready'",timeout=60000)
  await page.get_by_role('button',name='Close panel',exact=True).click()
  await page.get_by_role('button',name='Launch mission',exact=True).click()
  for _ in range(8):
   await page.wait_for_function("sim.useSim.getState().encounter!==null || sim.useSim.getState().status==='complete' || sim.useSim.getState().ppoPhase==='error'",timeout=45000)
   state=await page.evaluate(SNAPSHOT)
   if state['error']: raise RuntimeError(state['error'])
   if state['status']=='complete': break
   await page.evaluate('sim.useSim.getState().continueExploration()')
  assert await page.evaluate("sim.useSim.getState().status==='complete'")
  await snapshot('ppo-completed.png','Real checkpoint-driven Python mission rendered by the browser; development seed 10000.')
  final=await page.evaluate(SNAPSHOT)
  assert (final['step'],final['found'],final['total'])==(94,4,4),final
  (output/'capture-manifest.json').write_text(json.dumps({'kind':'actual browser captures','url':url,'browser':browser.version,'viewport_png':[1600,1000],'viewport_gif':[1280,800],'encoded_gif':[960,600],'page_errors':errors,'captures':records,'source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'frontend/src').rglob('*')) if f.suffix in ('.ts','.tsx','.css')}},indent=2)+'\n')
  assert not errors,errors
  await browser.close()

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--url',default='http://127.0.0.1:5173/')
 parser.add_argument('--output',type=Path,default=ROOT/'docs/media/frontend')
 args=parser.parse_args()
 asyncio.run(capture(args.url,args.output))
