"""Optional map picker checks; start Vite :5173 and PPO service :8765 first.

The earlier seed-range report is historical. This writes a separate map-controls
report only when explicitly run; UI no longer exposes raw seed fields.
"""
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
    assert await page.get_by_label('World seed',exact=True).count()==0
    await page.get_by_role('radio',name='PPO',exact=True).click()
    launch=page.get_by_role('button',name='Create mission',exact=True)
    await launch.wait_for(state='visible')
    picker=page.get_by_role('combobox',name='PPO map',exact=True)
    assert await picker.locator('option:checked').inner_text()=='Map 01'
    assert await page.get_by_label('PPO seed',exact=True).count()==0
    await page.get_by_role('button',name='Choose another PPO map',exact=True).click()
    assert await picker.input_value()!='10000'
    await picker.select_option('10001')
    await launch.click()
    await page.wait_for_function("document.querySelector('.objective-card')?.textContent.includes('Ready to explore')")
    # Check the option is really used by Python, not merely relabelled in the UI.
    await page.evaluate('''async()=>{const r=performance.getEntriesByType('resource');window.sim=await import(r.find(e=>e.name.includes('/src/store/simStore.ts')).name)}''')
    assert await page.evaluate('sim.useSim.getState().engine.scenario.seed')==10001
    await page.get_by_role('button',name='Open controls guide',exact=True).click()
    assert await page.get_by_text('Read the terrain.',exact=True).is_visible()
    await page.get_by_role('button',name='Close panel',exact=True).click()
    await page.screenshot(path=str(Path(tempfile.gettempdir())/'swarm-map-controls.png'))
    assert not errors,errors
    report={'generatedAt':datetime.now(timezone.utc).isoformat(),'rawSeedFieldsHidden':True,'friendlyMapLabels':True,'shuffleChoosesDifferentMap':True,'pythonMapSelectionApplied':True,'terrainExplanationAvailable':True,'errors':errors}
    (ROOT/'docs/validation/browser_map_controls_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    await browser.close()

asyncio.run(main())
