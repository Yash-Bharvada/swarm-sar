"""Seed range UI checks against Vite :5173 and the PPO service :8765."""
import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
async def main():
  async with async_playwright() as p:
    browser=await p.chromium.launch(channel='chrome',headless=True,args=['--use-angle=metal','--ignore-gpu-blocklist'])
    page=await browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    await page.goto('http://127.0.0.1:5173/')
    await page.get_by_role('button',name='Controller settings',exact=True).click()
    seed=page.get_by_role('spinbutton',name='PPO seed',exact=True)
    launch=page.get_by_role('button',name='New PPO mission',exact=True)
    await seed.fill('1000')
    assert await launch.is_disabled()
    assert await seed.get_attribute('aria-invalid')=='true'
    assert await page.get_by_text('Enter a whole number from 10000 to 10099 to launch.',exact=True).is_visible()
    await seed.fill('10099')
    assert await launch.is_enabled()
    assert await seed.get_attribute('aria-invalid')=='false'
    await page.get_by_role('button',name='Choose another PPO seed',exact=True).click()
    shuffled=int(await seed.input_value())
    assert 10000<=shuffled<=10099 and shuffled!=10099
    await seed.fill('10001')
    await launch.click()
    await page.wait_for_function("document.querySelector('.scene-tags')?.textContent.includes('10001')")
    await page.get_by_role('button',name='Launch mission',exact=True).wait_for(state='visible')
    await page.get_by_role('button',name='Open controls guide',exact=True).click()
    assert await page.get_by_text('Read the terrain.',exact=True).is_visible()
    assert await page.get_by_text('Low, loose debris is traversable:',exact=False).is_visible()
    await page.get_by_role('button',name='Close panel',exact=True).click()
    await page.screenshot(path=str(Path(tempfile.gettempdir())/'swarm-rubble-refined.png'))
    assert not errors,errors
    report={'generatedAt':datetime.now(timezone.utc).isoformat(),'invalid1000ExplainedAndBlocked':True,'upperBound10099Accepted':True,'shuffleSelectsDifferentAllowedSeed':True,'realPythonSeed10001Loaded':True,'terrainExplanationAvailable':True,'errors':errors,'scope':'UI seed validation and terrain presentation; no physics or training changes.'}
    (ROOT/'docs/browser_seed_terrain_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    await browser.close()

asyncio.run(main())
