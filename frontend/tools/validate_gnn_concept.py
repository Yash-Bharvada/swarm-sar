"""Real browser checks for the explicitly illustrative GNN view.

The example graph is never recorded as a trained model or live ROS result.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:5189')
    parser.add_argument('--output', default='artifacts/gnn_concept_ui')
    parser.add_argument('--browser-executable')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []

    def check(name, passed):
        assert passed, name
        checks.append(name)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.browser_executable,
                                     args=['--enable-unsafe-swiftshader'])
        page = browser.new_page(viewport={'width': 1512, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url + '/?mode=observatory')
        expect(page.locator('.observatory-canvas canvas')).to_be_visible(timeout=20000)
        page.evaluate("async()=>{const {useSim}=await import('/src/store/simStore.ts');window.__conceptStore=useSim}")
        before = page.evaluate("()=>{const s=window.__conceptStore.getState();return JSON.stringify([s.engine.stateHash(),s.engine.step,s.engine.commandLog,s.status])}")
        page.locator('.ob-stream-toggle').click()
        with page.expect_download() as initial_download:
            page.get_by_role('button', name='Export telemetry', exact=True).click()
        initial_export = json.loads(Path(initial_download.value.path()).read_text())
        page.get_by_role('button', name='Close messages', exact=True).click()
        page.get_by_role('button', name='GNN concept', exact=True).click()
        expect(page.get_by_text('GNN ARCHITECTURE · INTERACTIVE WALKTHROUGH', exact=True)).to_be_visible()
        expect(page.locator('.ob-source-note')).to_contain_text('not live inference')
        expect(page.get_by_role('img', name='Illustrative GNN graph with example messages and attention, not live inference')).to_be_visible()
        check('Concept is visibly and accessibly distinguished from live inference', True)
        page.get_by_role('button', name='Next step', exact=True).click()
        expect(page.locator('.ob-gnn-explanation b')).to_have_text('Pass messages')
        page.get_by_role('button', name='Next step', exact=True).click()
        expect(page.locator('.ob-gnn-explanation b')).to_have_text('Weight and aggregate')
        meter = page.get_by_label('Example attention rover_1', exact=True)
        original = float(meter.get_attribute('value'))
        slider = page.get_by_label('Example message score', exact=True)
        slider.fill('4')
        slider.dispatch_event('input')
        check('Example score changes normalized illustrative attention', float(meter.get_attribute('value')) > original)
        weights = page.locator('.ob-gnn-weight meter').evaluate_all('(meters)=>meters.map(m=>m.value)')
        check('Example attention includes self and sums to one', abs(sum(weights) - 1) < 1e-8)
        page.get_by_role('button', name='Inspect drone_2', exact=True).click()
        expect(page.locator('.ob-gnn-receiver strong')).to_have_text('Drone 2')
        check('Selecting another robot rebuilds the example receiver graph', True)
        page.wait_for_timeout(400)
        page.screenshot(path=str(output / 'desktop-gnn-illustration.png'), full_page=True)
        page.get_by_role('button', name='Next step', exact=True).click()
        expect(page.locator('.ob-gnn-explanation b')).to_have_text('Inform a decision')
        expect(page.get_by_text('Concept only · no robot commands', exact=True)).to_be_visible()
        page.get_by_role('button', name='Play illustration', exact=True).click()
        page.wait_for_timeout(2700)
        expect(page.locator('.ob-gnn-explanation b')).to_have_text('Build a local graph')
        page.get_by_role('button', name='Pause illustration', exact=True).click()
        after = page.evaluate("()=>{const s=window.__conceptStore.getState();return JSON.stringify([s.engine.stateHash(),s.engine.step,s.engine.commandLog,s.status])}")
        check('Illustration playback, selection and scores leave mission state and command log unchanged', before == after)
        page.locator('.ob-stream-toggle').click()
        with page.expect_download() as download:
            page.get_by_role('button', name='Export telemetry', exact=True).click()
        exported = json.loads(Path(download.value.path()).read_text())
        check('Example edges are excluded from real packet export', exported['packets'] == initial_export['packets'] and exported['metrics'] == initial_export['metrics'] and 'concept' not in exported)
        page.get_by_role('button', name='Close messages', exact=True).click()
        page.get_by_role('button', name='Peer network', exact=True).click()
        expect(page.locator('.ob-gnn-panel')).to_have_count(0)
        check('Actual peer network remains a separate view', True)
        page.get_by_role('button', name='3D map', exact=True).click()
        expect(page.get_by_role('button', name='3D map', exact=True)).to_have_attribute('aria-pressed', 'true')
        page.close()
        mobile = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, reduced_motion='reduce')
        mobile.on('pageerror', lambda error: errors.append(str(error)))
        mobile.goto(args.url + '/?mode=observatory')
        mobile.get_by_role('button', name='GNN concept', exact=True).click()
        expect(mobile.get_by_text('GNN ARCHITECTURE · INTERACTIVE WALKTHROUGH', exact=True)).to_be_visible()
        mobile.get_by_role('button', name='Next step', exact=True).click()
        mobile.get_by_role('button', name='Next step', exact=True).click()
        mobile.wait_for_timeout(400)
        check('Mobile concept view has no horizontal overflow', mobile.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        mobile.screenshot(path=str(output / 'mobile-gnn-illustration.png'), full_page=True)
        mobile.close()
        check('No browser script errors', not errors)
        browser.close()
    (output / 'verification.json').write_text(json.dumps({'checks': checks, 'passed': len(checks),
        'browser_errors': errors, 'scope': 'GNN teaching illustration; no live GNN inference, ROS or training claim.'}, indent=2) + '\n')
    print(json.dumps({'passed': len(checks), 'output': str(output), 'browser_errors': errors}))


if __name__ == '__main__':
    main()
