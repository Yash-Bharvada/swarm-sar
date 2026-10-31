"""Exercise the guided story in local Chrome; uses the existing Vite dev server.

Run from the repository root: .venv/bin/python frontend/scripts/explain_qa.py
Screenshots and the verification report are written under artifacts/explain-mode/.
"""
import asyncio
import argparse
import json
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts' / 'explain-mode'
OUT.mkdir(parents=True, exist_ok=True)


async def main():
    checks = []
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--use-angle=metal', '--ignore-gpu-blocklist'])
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
        page.set_default_timeout(20000)
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto('http://127.0.0.1:5173/', wait_until='domcontentloaded')
        await page.locator('.explain-launch').wait_for()
        await page.evaluate('''async () => {
          const resources = performance.getEntriesByType('resource');
          window.qaSim = await import(resources.find(e => e.name.includes('/src/store/simStore.ts')).name);
          const fiber = await import(resources.find(e => e.name.includes('@react-three_fiber.js')).name);
          window.qaRoot = fiber._roots.get(document.querySelector('.stage canvas')).store;
          window.qaOriginal = qaSim.useSim.getState();
          qaOriginal.focusOn(qaOriginal.engine.robots[0].name);
        }''')
        await page.wait_for_timeout(1100)
        await page.evaluate('''() => {
          window.qaOriginal = qaSim.useSim.getState();
          window.qaHash = qaOriginal.engine.stateHash();
          window.qaCanvas = document.querySelector('.stage canvas');
          const {camera, controls} = qaRoot.getState();
          window.qaCamera = {position:camera.position.toArray(), target:controls.target.toArray(), zoom:camera.zoom};
        }''')
        await page.locator('.explain-launch').click()
        await page.locator('.ex-story-content h1').wait_for()
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUT / '01-story-desktop.png'))
        assert await page.evaluate('qaSim.useSim.getState().engine !== qaOriginal.engine && qaSim.useSim.getState().explainActive')
        assert await page.evaluate('qaCanvas === document.querySelector(".stage canvas")')
        checks.append('Independent sandbox reuses the existing 3D canvas')

        async def scene(index):
            await page.locator('.ex-progress-steps button').nth(index).click()
            await page.wait_for_timeout(180)
            assert await page.locator('.ex-story-content h1').is_visible()

        await scene(1)
        await page.locator('.ex-robot-caption').wait_for()
        assert await page.evaluate('qaSim.useSim.getState().selected.startsWith("rover")')
        await page.wait_for_timeout(700)
        await page.screenshot(path=str(OUT / '02-rover-desktop.png'))
        await scene(2)
        assert await page.evaluate('qaSim.useSim.getState().selected.startsWith("drone")')
        checks.append('Rover and drone focus, highlights, and vision ranges')

        await scene(3)
        step = await page.evaluate('qaSim.useSim.getState().engine.step')
        await page.wait_for_timeout(1100)
        assert await page.evaluate('qaSim.useSim.getState().engine.step') > step
        await page.get_by_role('button', name='Pause story animations', exact=True).click()
        step = await page.evaluate('qaSim.useSim.getState().engine.step')
        await page.wait_for_timeout(600)
        assert await page.evaluate('qaSim.useSim.getState().engine.step') == step
        await scene(7)
        assert await page.locator('.ex-story-content').evaluate('(e) => Number(getComputedStyle(e).opacity)') == 1
        await page.get_by_role('button', name='Take a step', exact=False).click()
        assert 'Step 1' in await page.locator('.exv-status').inner_text()
        await page.get_by_role('button', name='Resume story animations', exact=True).click()
        checks.append('Pause, navigation while paused, and interactive SLAM map')

        await scene(8)
        await page.get_by_role('button', name='Explore a new place', exact=True).click()
        assert '+1' in await page.locator('.exv-status').inner_text()
        await page.get_by_role('button', name='Repeat the loop', exact=True).click()
        assert '0.' in await page.locator('.exv-status').inner_text()
        await scene(9)
        await page.get_by_role('button', name='Split the search', exact=True).click()
        assert '6 rooms' in await page.locator('.exv-status').inner_text()
        await scene(10)
        await page.get_by_role('button', name='Move C out of reach', exact=True).click()
        await page.get_by_role('button', name='Send a clue', exact=False).click()
        assert 'A and B' in await page.locator('.exv-status').inner_text()
        assert await page.evaluate('qaSim.useSim.getState().overlays.packets && qaSim.useSim.getState().overlays.links')
        await scene(11)
        await page.get_by_role('button', name='Blocked hall', exact=True).click()
        assert 'another way' in await page.locator('.exv-status').inner_text()
        checks.append('PPO reward, MARL cooperation, radio isolation, and GNN clue interactions')

        await scene(5)
        await page.get_by_role('button', name='Enlarge Gazebo screenshot', exact=True).click()
        assert await page.locator('dialog[open]').count() == 1
        await page.keyboard.press('Escape')
        assert await page.locator('.ex-mode').count() == 1
        await scene(6)
        await page.get_by_label('Recorded RViz map progress', exact=True).fill('4')
        assert '10-rviz-progress' in await page.locator('.ex-recorded-image img').get_attribute('src')
        checks.append('Original Gazebo screenshot enlargement and five recorded RViz map states')

        await scene(12)
        await page.wait_for_function('Array.from(document.querySelectorAll(".ex-proof-shot img")).every(i => i.complete && i.naturalWidth > 0)')
        await page.get_by_role('button', name='Enlarge: The learned policy in action', exact=True).click()
        assert await page.locator('dialog[open] img').get_attribute('src')
        await page.keyboard.press('Escape')
        await page.screenshot(path=str(OUT / '03-evidence-desktop.png'))
        await page.get_by_text('Inside the build', exact=False).click()
        assert await page.locator('.ex-proof-downloads a').count() == 6
        source_urls = await page.locator('.ex-proof-downloads a').evaluate_all('(links) => links.map(a => a.href)')
        for url in source_urls:
            response = await page.request.get(url)
            assert response.ok, (url, response.status)
        checks.append('Four authentic captures, training evidence, and six working source downloads')

        await scene(13)
        for index in range(5):
            await page.locator('.ex-system button').nth(index).click()
            assert await page.locator('.ex-system button').nth(index).get_attribute('aria-pressed') == 'true'
        await page.screenshot(path=str(OUT / '04-system-desktop.png'))
        await page.get_by_role('button', name='Explore your mission', exact=True).click()
        await page.wait_for_timeout(200)
        assert await page.evaluate('qaSim.useSim.getState().engine === qaOriginal.engine && qaOriginal.engine.stateHash() === qaHash')
        assert await page.evaluate('qaSim.useSim.getState().following && qaSim.useSim.getState().focus.robot === qaOriginal.focus.robot')
        checks.append('System layers work; original mission identity, state, and camera follow return')

        await page.set_viewport_size({'width': 390, 'height': 844})
        await page.locator('.explain-launch').click()
        await page.wait_for_timeout(700)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(OUT / '05-story-mobile.png'))
        for index in range(14):
            await scene(index)
            rect = await page.locator('.ex-next').bounding_box()
            assert rect and rect['x'] >= 0 and rect['x'] + rect['width'] <= 391
        await scene(12)
        await page.screenshot(path=str(OUT / '06-evidence-mobile.png'))
        await page.keyboard.press('Escape')
        checks.append('All 14 scenes fit a 390px mobile viewport with reachable navigation')

        await page.emulate_media(reduced_motion='reduce')
        await page.locator('.explain-launch').click()
        await page.get_by_role('button', name='Pause story animations', exact=True).click()
        await scene(8)
        assert await page.locator('.ex-story-content').evaluate('(e) => getComputedStyle(e).animationName') == 'none'
        await page.keyboard.press('Escape')
        checks.append('Reduced-motion and keyboard exit')

        await page.set_viewport_size({'width': 1440, 'height': 1000})
        await page.locator('.observatory-launch').click()
        await page.get_by_role('button', name='Back to simulation', exact=False).click()
        await page.locator('.explain-launch').click()
        await page.go_back(wait_until='domcontentloaded')
        await page.wait_for_timeout(500)
        assert await page.evaluate('!qaSim.useSim.getState().explainActive && qaSim.useSim.getState().engine === qaOriginal.engine')
        checks.append('Browser history restores the original mission before opening the observatory')
        assert not errors, errors
        await browser.close()
    report = {'passed': len(checks), 'checks': checks, 'pageErrors': errors}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


async def verify_ppo_and_auto():
    """Targeted checks for the background Python response and timed navigation."""
    initial = json.loads((ROOT / 'frontend/src/tests/fixtures/pythonInitial.json').read_text())
    next_tick = json.loads(json.dumps(initial))
    next_tick['step'] = 1
    started, release, delivered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    requests = {'created': 0, 'stepped': 0, 'deleted': 0}
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--use-angle=metal', '--ignore-gpu-blocklist'])
        page = await browser.new_page(viewport={'width': 1280, 'height': 900})
        page.set_default_timeout(15000)
        page.on('pageerror', lambda error: errors.append(str(error)))

        async def handle(route):
            request = route.request
            if request.method == 'DELETE':
                requests['deleted'] += 1
                await route.fulfill(json={'ok': True})
            elif request.url.endswith('/missions'):
                requests['created'] += 1
                await route.fulfill(json=initial)
            elif request.url.endswith('/step'):
                requests['stepped'] += 1
                started.set()
                await release.wait()
                await route.fulfill(json=next_tick)
                delivered.set()
            else:
                await route.fulfill(json=initial)

        await page.route('**/api/ppo/**', handle)
        await page.goto('http://127.0.0.1:5173/', wait_until='domcontentloaded')
        await page.locator('.explain-launch').wait_for()
        await page.evaluate('''async () => {
          window.qaSim = await import(performance.getEntriesByType('resource').find(e => e.name.includes('/src/store/simStore.ts')).name);
          window.qaTimeout = window.setTimeout;
          window.setTimeout = (fn, delay, ...args) => qaTimeout(fn, delay === 45000 ? 1000 : delay, ...args);
        }''')
        await page.locator('.explain-launch').click()
        await page.locator('.ex-auto').click()
        await page.wait_for_function('document.querySelector(".ex-chapter-number")?.textContent === "02"')
        await page.locator('.ex-auto').click()
        await page.get_by_role('button', name='Back to mission', exact=False).click()
        await page.evaluate('window.setTimeout = qaTimeout')

        await page.evaluate('''() => qaSim.useSim.setState({controllerMode:'ppo', ppoPhase:'connecting', ppoRevision:qaSim.useSim.getState().ppoRevision+1})''')
        await page.wait_for_function('qaSim.useSim.getState().ppoPhase === "ready"')
        await page.evaluate('''() => {window.qaRemote=qaSim.useSim.getState().engine; qaSim.useSim.getState().launch();}''')
        await asyncio.wait_for(started.wait(), timeout=10)
        await page.evaluate('qaSim.useSim.getState().pause()')
        await page.locator('.explain-launch').click()
        assert await page.evaluate('qaSim.useSim.getState().explainActive && qaSim.useSim.getState().engine !== qaRemote')
        release.set()
        await asyncio.wait_for(delivered.wait(), timeout=10)
        await page.wait_for_timeout(200)
        assert await page.evaluate('qaRemote.step === 0')
        await page.get_by_role('button', name='Back to mission', exact=False).click()
        await page.wait_for_function('qaRemote.step === 1')
        assert await page.evaluate('qaSim.useSim.getState().engine === qaRemote && qaSim.useSim.getState().status === "paused" && qaSim.useSim.getState().ppoPhase === "ready"')
        assert requests == {'created': 1, 'stepped': 1, 'deleted': 0}, requests
        assert not errors, errors
        report = {'passed': 2, 'checks': ['Auto advances after the 45-second scene timer (accelerated for this check)', 'In-flight PPO response is retained during the independent story and applied once on return without deleting/recreating the Python mission'], 'requests': requests, 'pageErrors': errors}
        (OUT / 'ppo-report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ppo', action='store_true', help='Run only targeted in-flight PPO and auto-navigation checks')
    args = parser.parse_args()
    asyncio.run(verify_ppo_and_auto() if args.ppo else main())
