"""Real wheel anchoring, reversal and drawer-resize regression checks on Vite :5173.
Requires Python Playwright and installed Chrome.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
  async with async_playwright() as p:
    browser = await p.chromium.launch(channel='chrome', headless=True, args=['--use-angle=metal','--ignore-gpu-blocklist'])
    page = await browser.new_page(viewport={'width':1440,'height':1000})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    await page.goto('http://127.0.0.1:5173/')
    await page.get_by_role('button', name='Launch mission', exact=True).wait_for()
    await page.evaluate('''async()=>{const r=performance.getEntriesByType('resource'),f=await import(r.find(e=>e.name.includes('@react-three_fiber.js')).name);window.root=f._roots.get(document.querySelector('canvas')).store;window.math=await import(r.find(e=>e.name.includes('/src/scene/cameraMath.ts')).name)}''')
    bounds = await page.locator('canvas').bounding_box()
    await page.mouse.move(bounds['x']+bounds['width']*.68, bounds['y']+bounds['height']*.48)
    await page.evaluate('''()=>{const c=root.getState().camera;window.startZoom=c.zoom;window.anchor=math.captureGroundAnchor(c,{x:.36,y:.04,clone(){return this}});window.samples=[];window.collect=true;function sample(){if(!collect)return;samples.push(c.zoom);requestAnimationFrame(sample)}sample()}''')
    await page.mouse.wheel(0,-180)
    await page.wait_for_timeout(1100)
    first = await page.evaluate('''()=>{const c=root.getState().camera,p=anchor.point.clone().project(c);return {zoom:c.zoom,start:startZoom,error:Math.hypot(p.x-.36,p.y-.04),samples:[...samples]}}''')
    assert first['zoom']>first['start'] and first['error']<0.001,first
    assert all(b>=a-1e-6 for a,b in zip(first['samples'],first['samples'][1:])),first
    # Opening/closing the drawer must preserve actual world scale.
    await page.get_by_role('button', name='Open fleet panel',exact=True).click()
    await page.wait_for_timeout(350)
    after = await page.evaluate('root.getState().camera.zoom')
    assert abs(after-first['zoom'])<.01,(after,first['zoom'])
    await page.get_by_role('button',name='Close panel',exact=True).click()
    await page.wait_for_timeout(350)
    await page.mouse.move(bounds['x']+bounds['width']*.68,bounds['y']+bounds['height']*.48)
    await page.mouse.wheel(0,180)
    await page.wait_for_timeout(1100)
    final = await page.evaluate('({zoom:root.getState().camera.zoom,start:startZoom})')
    assert abs(final['zoom']-final['start'])<.01,final
    assert not errors,errors
    await page.evaluate('collect=false')
    report={'wheelAnchorErrorNdc':first['error'],'monotonicZoom':True,'drawerPreservesScale':True,'reverseRestoresZoom':True,'errors':errors,'browserVersion':browser.version}
    (Path(__file__).resolve().parents[2]/'docs/validation/browser_zoom_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    await browser.close()

asyncio.run(main())
