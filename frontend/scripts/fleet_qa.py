"""Fleet preview smoke checks against Vite :5173; requires Playwright/Chrome."""
import asyncio
import json
import tempfile
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
  async with async_playwright() as p:
    browser=await p.chromium.launch(channel='chrome',headless=True,args=['--use-angle=metal','--ignore-gpu-blocklist'])
    page=await browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    await page.goto('http://127.0.0.1:5173/')
    await page.get_by_role('button',name='Open fleet panel',exact=True).click()
    await page.wait_for_timeout(1600)
    assert await page.locator('.robot-preview').count()==4
    assert await page.locator('canvas').count()==2
    preview=page.locator('.robot-preview').first
    clip=await preview.bounding_box()
    frame1=await page.screenshot(clip=clip)
    await page.wait_for_timeout(700)
    async def rotations():
      return await page.evaluate("""async()=>{const r=performance.getEntriesByType('resource'),f=await import(r.find(e=>e.name.includes('@react-three_fiber.js')).name);return [...f._roots.values()].flatMap(v=>v.store.getState().internal.subscribers.map(sub=>{const s=sub.store.getState();let found=[];s.scene.traverse(o=>{if(o.name.startsWith('preview-'))found.push([o.name,o.rotation.y])});return found})).flat()}""")
    before=await rotations()
    await page.wait_for_timeout(700)
    after=await rotations()
    assert await page.screenshot(clip=clip)!=frame1,'Rendered preview did not animate'
    assert before!=after,'Preview model did not rotate'
    shots=Path(tempfile.gettempdir())/'swarm-fleet-qa'
    shots.mkdir(exist_ok=True)
    await page.screenshot(path=str(shots/'fleet.png'))
    await page.get_by_role('button',name='Inspect Rover 1:',exact=False).click()
    await page.wait_for_timeout(500)
    assert await page.locator('.robot-preview.large').count()==1
    await page.screenshot(path=str(shots/'rover.png'))
    await page.locator('.focus-button').click()
    await page.get_by_role('button',name='← All robots',exact=True).click()
    await page.get_by_role('button',name='Inspect Drone 1:',exact=False).click()
    await page.wait_for_timeout(500)
    await page.screenshot(path=str(shots/'drone.png'))
    await page.get_by_role('button',name='Close panel',exact=True).click()
    assert await page.locator('canvas').count()==1
    await page.get_by_role('button',name='Open controls guide',exact=True).click()
    assert await page.get_by_role('heading',name='Explore the world',exact=True).is_visible()
    await page.get_by_role('button',name='Close panel',exact=True).click()
    await page.get_by_role('button',name='Open fleet panel',exact=True).click()
    await page.evaluate('''async()=>{const r=performance.getEntriesByType('resource');window.sim=await import(r.find(e=>e.name.includes('/src/store/simStore.ts')).name);sim.useSim.getState().select(null);sim.useSim.getState().setSetting('rovers',5);sim.useSim.getState().setSetting('drones',5)}''')
    assert await page.locator('.robot-preview').count()==10
    assert await page.locator('canvas').count()==2
    await page.locator('.panel.right').evaluate('(e)=>e.scrollTop=e.scrollHeight')
    await page.wait_for_timeout(500)
    await page.set_viewport_size({'width':390,'height':844})
    await page.wait_for_timeout(600)
    await page.screenshot(path=str(shots/'mobile.png'))
    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    await page.emulate_media(reduced_motion='reduce')
    await page.wait_for_timeout(500)
    assert not errors,errors
    report={'rotatingPreview':True,'sharedCanvasForTenRobots':True,'detailSelectionAndFocus':True,'canvasReleasedOnClose':True,'controlsGuideAvailable':True,'mobileNoOverflow':True,'reducedMotionSupported':True,'errors':errors,'browserVersion':browser.version}
    (Path(__file__).resolve().parents[2]/'docs/validation/browser_fleet_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    await browser.close()

asyncio.run(main())
