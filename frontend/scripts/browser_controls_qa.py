"""Optional Chromium QA against the Vite development server.

From frontend/: npm run dev -- --host 127.0.0.1 --port 5174
Then from the repository: python3 frontend/scripts/browser_controls_qa.py
Requires Python Playwright and a local Chrome install; no test hooks ship in the app.
Screenshots go to a temporary directory and the checked report goes to docs/.
"""
import argparse
import asyncio
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:5174/')
parser.add_argument('--output', type=Path, default=ROOT / 'docs/browser_controls_validation.json')
args = parser.parse_args()
SCREENSHOTS = Path(tempfile.gettempdir()) / 'swarm-controls-qa'
SCREENSHOTS.mkdir(exist_ok=True)
from playwright.async_api import async_playwright

async def main():
  async with async_playwright() as p:
    browser=await p.chromium.launch(channel='chrome',headless=True,args=['--use-angle=metal','--ignore-gpu-blocklist'])
    page=await browser.new_page(viewport={'width':1440,'height':1000}, device_scale_factor=1)
    page.set_default_timeout(15000)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    await page.goto(args.url,wait_until='domcontentloaded')
    await page.get_by_role('button',name='Launch mission',exact=True).wait_for()
    await page.wait_for_timeout(700)
    await page.evaluate('''async()=>{const resources=performance.getEntriesByType('resource');window.qaSim=await import(resources.find(e=>e.name.includes('/src/store/simStore.ts')).name);const f=await import(resources.find(e=>e.name.includes('@react-three_fiber.js')).name);window.qaRoot=f._roots.get(document.querySelector('.stage canvas')).store;window.qaScenario=await import(resources.find(e=>e.name.includes('/src/simulation/world/ScenarioGenerator.ts')).name)}''')
    await page.get_by_role('button',name='Open mission panel',exact=True).click()
    field=page.get_by_label('Survivor count',exact=True)
    await field.fill('100')
    await page.get_by_role('button',name='Apply count',exact=True).click()
    assert await page.evaluate('qaSim.useSim.getState().engine.scenario.victims.length')==100
    await page.screenshot(path=str(SCREENSHOTS / 'survivor-controls.png'))
    await page.get_by_text('Placement options',exact=True).click()
    await page.get_by_role('button',name='Clear survivors',exact=True).click()
    assert await page.get_by_role('button',name='Launch mission',exact=True).is_disabled()
    await page.get_by_role('button',name='Place on map',exact=True).click()
    await page.wait_for_timeout(600)
    assert await page.locator('.workspace-drawer').count()==0
    await page.get_by_role('button',name='Zoom in',exact=True).click()
    await page.wait_for_timeout(1100)
    before=await page.evaluate('''()=>{const {camera,controls}=qaRoot.getState();return {zoom:camera.zoom,pos:camera.position.toArray(),target:controls.target.toArray()}}''')
    point=await page.evaluate('''()=>{const s=qaSim.useSim.getState();const c=qaScenario.survivorPlacementCells(s.engine.scenario);const point=c.find(p=>p.x>s.engine.scenario.width*.45 && p.x<s.engine.scenario.width*.7 && p.y>s.engine.scenario.height*.3 && p.y<s.engine.scenario.height*.55);const v=qaRoot.getState().camera.position.clone().set(point.x-s.engine.scenario.width/2+.5,0,point.y-s.engine.scenario.height/2+.5).project(qaRoot.getState().camera);return {...point,ndcX:v.x,ndcY:v.y}}''')
    rect=await page.locator('.stage canvas').bounding_box()
    x=rect['x']+(point['ndcX']+1)*rect['width']/2
    y=rect['y']+(1-point['ndcY'])*rect['height']/2
    await page.mouse.click(x,y)
    await page.wait_for_timeout(400)
    assert await page.evaluate('qaSim.useSim.getState().engine.scenario.victims.length')==1
    after=await page.evaluate('''()=>{const {camera,controls}=qaRoot.getState();return {zoom:camera.zoom,pos:camera.position.toArray(),target:controls.target.toArray()}}''')
    assert abs(before['zoom']-after['zoom'])<.001, {'before':before,'after':after}
    assert max(abs(a-b) for a,b in zip(before['target'],after['target']))<.001
    await page.screenshot(path=str(SCREENSHOTS / 'placement-editor.png'))
    await page.mouse.click(x,y-3)
    await page.wait_for_timeout(250)
    assert await page.evaluate('qaSim.useSim.getState().engine.scenario.victims.length')==0
    await page.mouse.click(x,y)
    await page.get_by_role('button',name='Done placing',exact=True).click()
    assert await page.locator('.placement-banner').count()==0
    await page.wait_for_function("!qaRoot.getState().scene.getObjectByName('survivor-placement-markers')")
    await page.get_by_role('button',name='Launch mission',exact=True).click()
    await page.get_by_role('button',name='Open fleet panel',exact=True).click()
    await page.get_by_role('button',name='Inspect Rover 1:',exact=False).click()
    await page.locator('.focus-button').click()
    await page.wait_for_timeout(1300)
    assert await page.evaluate('qaSim.useSim.getState().following')
    tracking=await page.evaluate('''()=>{const s=qaSim.useSim.getState(),r=s.engine.robots.find(r=>r.name===s.selected);const p=qaRoot.getState().controls.target.clone().set(r.x-s.engine.scenario.width/2+.5,0,r.y-s.engine.scenario.height/2+.5);return {target:qaRoot.getState().controls.target.toArray(),robot:p.toArray(),step:s.engine.step}}''')
    await page.wait_for_timeout(1500)
    tracking2=await page.evaluate('''()=>{const s=qaSim.useSim.getState(),r=s.engine.robots.find(r=>r.name===s.selected);const p=qaRoot.getState().controls.target.clone().set(r.x-s.engine.scenario.width/2+.5,0,r.y-s.engine.scenario.height/2+.5);return {target:qaRoot.getState().controls.target.toArray(),robot:p.toArray(),step:s.engine.step,following:s.following}}''')
    assert tracking2['following'] and tracking2['step']>tracking['step']
    assert sum((a-b)**2 for a,b in zip(tracking2['target'],tracking2['robot']))<5,tracking2
    await page.get_by_role('button',name='Pause mission',exact=True).click()
    candidate = await page.evaluate("""()=>{const s=qaSim.useSim.getState(),c=qaRoot.getState().camera;return s.engine.robots.filter(r=>r.name!==s.selected).map(r=>{const prev=s.engine.prevPositions.get(r.id)??r,alpha=qaSim.simClock.alpha;const p=c.position.clone().set(prev.x+(r.x-prev.x)*alpha-s.engine.scenario.width/2+.5,r.type==='drone'?1.25:.45,prev.y+(r.y-prev.y)*alpha-s.engine.scenario.height/2+.5).project(c);return {name:r.name,x:p.x,y:p.y}}).find(p=>Math.abs(p.x)<.75&&Math.abs(p.y)<.65)}""")
    assert candidate, 'Expected a second robot within the focused view'
    rect=await page.locator('.stage canvas').bounding_box()
    await page.mouse.click(rect['x']+(candidate['x']+1)*rect['width']/2,rect['y']+(1-candidate['y'])*rect['height']/2)
    await page.wait_for_timeout(900)
    assert await page.evaluate("qaSim.useSim.getState().focus?.robot===qaSim.useSim.getState().selected && qaSim.useSim.getState().following")
    assert await page.evaluate('qaSim.useSim.getState().selected')==candidate['name']
    await page.get_by_role('button',name='Resume mission',exact=True).click()
    await page.get_by_role('button',name='Close panel',exact=True).click()
    await page.get_by_role('button',name='Watch maze',exact=False).click()
    await page.wait_for_timeout(600)
    assert await page.locator('.topbar,.command-rail,.hud,.robot-tag,.survivor-saved-tag,.workspace-drawer').count()==0
    assert await page.evaluate('qaSim.useSim.getState().following')
    await page.screenshot(path=str(SCREENSHOTS / 'clean-view.png'))
    await page.keyboard.press('Escape')
    assert await page.locator('.topbar').count()==1
    await page.keyboard.press('h')
    await page.get_by_role('button',name='Show interface',exact=True).click()
    assert await page.locator('.topbar').count()==1
    await page.get_by_role('button',name='Pause mission',exact=True).click()
    await page.set_viewport_size({'width':390,'height':844})
    await page.wait_for_timeout(500)
    assert await page.evaluate('document.body.scrollWidth')==390
    await page.keyboard.press('h')
    await page.wait_for_timeout(400)
    assert await page.locator('.topbar,.hud').count()==0
    await page.screenshot(path=str(SCREENSHOTS / 'clean-view-mobile.png'))
    await page.keyboard.press('Escape')
    report={'customCount100':True,'clickAddRemove':True,'editorCameraPreserved':True,'placementHiddenOnExit':True,'focusTracksMovingRobot':True,'focusTransfersToAnotherRobot':True,'focusPersistsInCleanView':True,'cleanModeKeyboardAndRestore':True,'mobileNoOverflow':True,'consoleErrors':errors}
    report.update({
      'reviewDate': '2026-10-29',
      'generatedAt': datetime.now(timezone.utc).isoformat(),
      'baseCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
      'scope': 'Vite development build, Chrome desktop 1440x1000 and mobile viewport 390x844; not physical hardware validation.',
      'reproduce': 'python3 frontend/scripts/browser_controls_qa.py --url http://127.0.0.1:5174/',
      'browserVersion': browser.version,
      'sourceHashes': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((ROOT / 'frontend/src').rglob('*')) if path.suffix in {'.ts', '.tsx', '.css'}},
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key != 'sourceHashes'},indent=2),flush=True)
    assert not errors
    await browser.close()
asyncio.run(main())
