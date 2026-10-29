"""Discovery-story browser checks. Run with Vite at 127.0.0.1:5173.
Requires Python Playwright and installed Chrome. Screenshots use a temp directory.
"""
import asyncio
import hashlib
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
SHOTS = Path(tempfile.gettempdir()) / 'swarm-survivor-qa'
SHOTS.mkdir(exist_ok=True)

async def main():
  async with async_playwright() as p:
    browser = await p.chromium.launch(channel='chrome', headless=True, args=['--use-angle=metal', '--ignore-gpu-blocklist'])
    page = await browser.new_page(viewport={'width':1440,'height':1000})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    await page.goto('http://127.0.0.1:5173/')
    await page.get_by_role('button', name='Launch mission', exact=True).wait_for()
    await page.evaluate('''async()=>{const r=performance.getEntriesByType('resource');window.qaSim=await import(r.find(e=>e.name.includes('/src/store/simStore.ts')).name);const f=await import(r.find(e=>e.name.includes('@react-three_fiber.js')).name);window.qaRoot=f._roots.get(document.querySelector('.stage canvas')).store;}''')
    await page.wait_for_function("qaRoot.getState().scene.getObjectByName('awaiting-survivor-beacons')?.count > 0")
    initial = await page.evaluate("({count:qaRoot.getState().scene.getObjectByName('awaiting-survivor-beacons').count,total:qaSim.useSim.getState().engine.scenario.victims.length,known:qaSim.useSim.getState().engine.survivorsFound()})")
    assert initial['count'] == initial['total'] and initial['known'] == 0, initial
    await page.get_by_role('button', name='Launch mission', exact=True).click()
    await page.evaluate('''()=>{for(let i=0;i<500&&!qaSim.useSim.getState().encounter;i++)qaSim.useSim.getState().advance(8)}''')
    await page.get_by_role('dialog').wait_for()
    await page.wait_for_timeout(1400)
    first = await page.evaluate('''()=>{const s=qaSim.useSim.getState(),v=s.engine.discoveredSurvivors().find(v=>v.id===s.encounter.id),r=qaRoot.getState();return {id:v.id,step:s.engine.step,zoom:s.cameraZoom,target:r.controls.target.toArray(),expected:[v.x-s.engine.scenario.width/2+.5,.65,v.y-s.engine.scenario.height/2+.5],status:s.status}}''')
    assert first['status']=='paused' and first['zoom'] >= 395,first
    assert max(abs(a-b) for a,b in zip(first['target'],first['expected']))<.1,first
    assert await page.evaluate('Math.abs(qaRoot.getState().camera.position.y-qaRoot.getState().controls.target.y)/(qaRoot.getState().camera.position.z-qaRoot.getState().controls.target.z)') < .6
    story = await page.locator('#encounter-story').inner_text()
    await page.keyboard.press('Space')
    # Focus lands on Continue; Space intentionally activates the accessible button.
    if not await page.get_by_role('dialog').count():
      await page.evaluate('qaSim.useSim.getState().inspectSurvivor('+str(first['id'])+')')
    await page.wait_for_timeout(400)
    stable = await page.evaluate('qaSim.useSim.getState().engine.step')
    await page.wait_for_timeout(400)
    assert stable == await page.evaluate('qaSim.useSim.getState().engine.step')
    await page.screenshot(path=str(SHOTS/'discovery-desktop.png'))
    await page.get_by_role('button',name='Continue exploration',exact=True).click()
    await page.wait_for_timeout(900)
    assert await page.evaluate('qaSim.useSim.getState().cameraZoom')<=105
    # Open only by tapping the confirmed human's accessible label.
    await page.evaluate('qaSim.useSim.getState().pause()')
    await page.get_by_role('button',name=f'Talk to survivor {first["id"]+1}',exact=True).click()
    assert await page.locator('#encounter-story').inner_text()==story
    await page.get_by_role('button',name='Continue exploration',exact=True).click()
    assert await page.evaluate('qaSim.useSim.getState().status')=='paused'
    await page.evaluate('qaSim.useSim.getState().resume()')
    seen = [first['id']]
    for _ in range(initial['total']+2):
      await page.evaluate('''()=>{for(let i=0;i<500&&qaSim.useSim.getState().status==='running';i++)qaSim.useSim.getState().advance(8)}''')
      current = await page.evaluate('({id:qaSim.useSim.getState().encounter?.id,status:qaSim.useSim.getState().status})')
      if current['status']=='complete': break
      assert 'id' in current,current
      seen.append(current['id'])
      await page.get_by_role('dialog').get_by_role('button').click()
    assert len(set(seen))==initial['total'],seen
    assert await page.evaluate('qaSim.useSim.getState().status')=='complete'
    assert await page.get_by_text('Everyone accounted for.',exact=True).count()==1
    # Completed humans can be revisited; the report returns without restarting.
    await page.evaluate('qaSim.useSim.getState().inspectSurvivor('+str(first['id'])+')')
    await page.set_viewport_size({'width':390,'height':844})
    await page.wait_for_timeout(1100)
    assert await page.evaluate('qaRoot.getState().camera.zoom') >= 39
    await page.screenshot(path=str(SHOTS/'discovery-mobile.png'))
    bounds = await page.get_by_role('dialog').bounding_box()
    assert bounds['x']>=0 and bounds['x']+bounds['width']<=391,bounds
    assert bounds['y']>=0 and bounds['y']+bounds['height']<844,bounds
    await page.get_by_role('button',name='View mission report',exact=True).click()
    assert await page.evaluate('qaSim.useSim.getState().status')=='complete'
    await page.evaluate('qaSim.useSim.getState().reset();qaSim.useSim.getState().toggleOverlay("coverage");qaSim.useSim.getState().launch()')
    await page.wait_for_timeout(700)
    await page.screenshot(path=str(SHOTS/'coverage-mobile.png'))
    await page.evaluate('qaSim.useSim.getState().reset();qaSim.useSim.getState().toggleCleanView();qaSim.useSim.getState().launch();for(let i=0;i<500&&!qaSim.useSim.getState().encounter;i++)qaSim.useSim.getState().advance(8)')
    await page.get_by_role('dialog').wait_for()
    assert await page.evaluate('qaSim.useSim.getState().cleanView')
    assert not errors,errors
    report = {'generatedAt':datetime.now(timezone.utc).isoformat(),'browserVersion':browser.version,'initialBeacons':initial,'firstDiscovery':first,'allSurvivorsShown':seen,'storyStableOnTap':True,'pausedUntilContinue':True,'overviewRestored':True,'mobileDialogVisible':True,'completedMissionRevisit':True,'cleanViewDiscoveryWorks':True,'errors':errors,'scope':'Chrome UI and real autonomous simulation discovery; not field rescue validation.','sourceHashes':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'frontend/src').rglob('*')) if f.suffix in ('.ts','.tsx','.css')}}
    (ROOT/'docs/validation/browser_survivor_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='sourceHashes'},indent=2))
    await browser.close()

asyncio.run(main())
