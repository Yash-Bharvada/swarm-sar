"""Optional real Web Audio interaction checks against a running Vite dev server.

Start: cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
Run: python3 frontend/scripts/audio_qa.py --full-cycle
Requires Python Playwright and a local Chrome installation. No app debug hooks.
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
parser.add_argument('--url', default='http://127.0.0.1:5173/')
parser.add_argument('--output', type=Path, default=ROOT / 'docs/validation/browser_audio_validation.json')
parser.add_argument('--full-cycle', action='store_true', help='Also sample a complete 31-second soundtrack progression')
args = parser.parse_args()
SCREENSHOTS = Path(tempfile.gettempdir()) / 'swarm-audio-qa'
SCREENSHOTS.mkdir(exist_ok=True)
from playwright.async_api import async_playwright

async def main():
  async with async_playwright() as p:
    browser=await p.chromium.launch(channel='chrome',headless=True,args=['--use-angle=metal','--ignore-gpu-blocklist'])
    page=await browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
    page.set_default_timeout(15000)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda message: errors.append(message.text) if message.type=='error' else None)
    await page.goto(args.url,wait_until='domcontentloaded')
    await page.get_by_role('button',name='Enable audio',exact=True).wait_for()
    await page.wait_for_timeout(600)
    await page.evaluate('''async()=>{const r=performance.getEntriesByType('resource');window.qaAudio=await import(r.find(e=>e.name.includes('/src/audio/Soundscape.ts')).name);window.qaPrefs=await import(r.find(e=>e.name.includes('/src/audio/audioStore.ts')).name);window.qaSim=await import(r.find(e=>e.name.includes('/src/store/simStore.ts')).name)}''')
    initial=await page.evaluate('qaAudio.soundscape.diagnostics()')
    assert initial['state']=='not-created',initial
    before=await page.evaluate('qaSim.useSim.getState().engine.stateHash()')
    await page.get_by_role('button',name='Enable audio',exact=True).click()
    await page.wait_for_function("qaAudio.soundscape.diagnostics().state==='running'")
    await page.wait_for_function("qaAudio.soundscape.diagnostics().scheduledBeat>=2 && qaAudio.soundscape.diagnostics().rms>0.0001")
    music=await page.evaluate('qaAudio.soundscape.diagnostics()')
    assert music['rms']>0.0001,music
    assert before==await page.evaluate('qaSim.useSim.getState().engine.stateHash()')
    cycle=None
    if args.full_cycle:
      cycle=await page.evaluate("""()=>new Promise(resolve=>{const samples=[];const stop=qaAudio.soundscape.context.currentTime+31;const id=setInterval(()=>{const s=qaAudio.soundscape,d=s.diagnostics();samples.push({rms:d.rms,tones:d.activeTones});if(s.context.currentTime>=stop){clearInterval(id);resolve({samples:samples.length,minRms:Math.min(...samples.map(s=>s.rms)),maxTones:Math.max(...samples.map(s=>s.tones)),beats:s.beat})}},200)})""")
      assert cycle['minRms']>0.00001 and cycle['maxTones']<48 and cycle['beats']>=35,cycle
    await page.evaluate('qaAudio.soundscape.visibility(true)')
    await page.wait_for_function("qaAudio.soundscape.diagnostics().state==='suspended'")
    await page.evaluate('qaAudio.soundscape.visibility(false)')
    await page.wait_for_function("qaAudio.soundscape.diagnostics().state==='running'")
    await page.screenshot(path=str(SCREENSHOTS / 'settings.png'))
    await page.get_by_label('Ambient music',exact=True).focus()
    await page.keyboard.press('m')
    assert await page.evaluate('qaPrefs.useAudio.getState().muted')
    await page.keyboard.press('m')
    assert not await page.evaluate('qaPrefs.useAudio.getState().muted')
    await page.keyboard.press('Home')
    assert await page.evaluate('qaPrefs.useAudio.getState().levels.music')==0
    await page.get_by_label('Ambient music',exact=True).press('ArrowRight')
    assert await page.evaluate('qaPrefs.useAudio.getState().levels.music')==.01
    await page.evaluate("qaPrefs.useAudio.getState().setVolume('music',.45)")
    await page.get_by_label('Master volume',exact=True).focus()
    await page.keyboard.press('Home')
    await page.wait_for_timeout(1000)
    zero=await page.evaluate('qaAudio.soundscape.diagnostics()')
    assert zero['rms']<0.00001,zero
    await page.evaluate("qaPrefs.useAudio.getState().setVolume('master',.55)")
    await page.get_by_role('button',name='Sound settings',exact=True).click()
    await page.get_by_role('button',name='Launch mission',exact=True).click()
    await page.wait_for_timeout(600)
    await page.get_by_role('button',name='Open fleet panel',exact=True).click()
    await page.get_by_role('button',name='Inspect Rover 1:',exact=False).click()
    await page.wait_for_timeout(180)
    await page.locator('.focus-button').click()
    await page.wait_for_timeout(500)
    rover=await page.evaluate('qaAudio.soundscape.diagnostics()')
    assert rover['played'].get('launch',0)>=1 and rover['played'].get('focusRover',0)>=1,rover
    assert rover['activeVehicles']==4
    await page.get_by_role('button',name='← All robots',exact=True).click()
    await page.get_by_role('button',name='Inspect Drone 1:',exact=False).click()
    await page.wait_for_timeout(180)
    await page.locator('.focus-button').click()
    await page.wait_for_timeout(300)
    drone=await page.evaluate('qaAudio.soundscape.diagnostics()')
    assert drone['played'].get('focusDrone',0)>=1,drone
    await page.get_by_role('button',name='Close panel',exact=True).click()
    await page.get_by_role('button',name='Pause mission',exact=True).click()
    await page.wait_for_timeout(400)
    await page.get_by_role('button',name='Mute audio',exact=True).click()
    await page.wait_for_timeout(1000)
    muted=await page.evaluate('qaAudio.soundscape.diagnostics()')
    assert muted['rms']<0.00001,muted
    await page.keyboard.press('m')
    await page.wait_for_timeout(350)
    assert await page.evaluate('qaPrefs.useAudio.getState().muted')==False
    await page.evaluate('''()=>{const s=qaSim.useSim.getState();while(!s.engine.survivorsFound()&&!s.engine.done)s.engine.tick();qaSim.useSim.setState({version:s.version+1})}''')
    await page.wait_for_timeout(400)
    found=await page.evaluate('qaAudio.soundscape.diagnostics()')
    assert found['played'].get('survivor',0)>=1,found
    found_count=found['played']['survivor']
    await page.evaluate("qaSim.useSim.getState().setSetting('quality','low')")
    await page.wait_for_timeout(450)
    assert (await page.evaluate('qaAudio.soundscape.diagnostics()'))['played']['survivor']==found_count
    await page.evaluate('''()=>{const s=qaSim.useSim.getState();while(!s.engine.done)s.engine.tick();qaSim.useSim.setState({version:s.version+1,status:'complete'})}''')
    await page.wait_for_timeout(500)
    complete=await page.evaluate('qaAudio.soundscape.diagnostics()')
    assert complete['played'].get('complete',0)>=1,complete
    await page.keyboard.press('h')
    await page.wait_for_timeout(350)
    assert await page.evaluate('qaPrefs.useAudio.getState().enabled')
    await page.keyboard.press('m')
    assert await page.evaluate('qaPrefs.useAudio.getState().muted')
    await page.keyboard.press('m')
    await page.keyboard.press('Escape')
    await page.evaluate('qaSim.useSim.getState().reset()')
    await page.wait_for_timeout(500)
    reset=await page.evaluate('qaAudio.soundscape.diagnostics()')
    assert reset['activeVehicles']==4 and reset['played'].get('reset',0)>=1,reset
    await page.set_viewport_size({'width':390,'height':844})
    await page.get_by_role('button',name='Sound settings',exact=True).click()
    await page.wait_for_timeout(300)
    await page.screenshot(path=str(SCREENSHOTS / 'mobile.png'))
    box=await page.locator('.sound-panel').bounding_box()
    assert box['x']>=0 and box['x']+box['width']<=390,box
    assert await page.evaluate('document.body.scrollWidth')==390
    await page.reload(wait_until='domcontentloaded')
    await page.get_by_role('button',name='Enable audio',exact=True).wait_for()
    assert await page.evaluate('''async()=>{const r=performance.getEntriesByType('resource');const {useAudio}=await import(r.find(e=>e.name.includes('/src/audio/audioStore.ts')).name);return useAudio.getState().enabled}''')==False
    report={'startsOnlyAfterEnable':True,'musicNonzeroRms':music['rms'],'masterZeroRms':zero['rms'],'mutedRms':muted['rms'],'independentSliders':True,'distinctRoverAndDroneFocusCues':True,'survivorAndCompletionCues':True,'noSurvivorReplayOnQualityChange':True,'resetVoiceCount':reset['activeVehicles'],'musicSurvivesCleanViewAndMWorks':True,'mobileNoOverflow':True,'reloadDoesNotAutoplay':True,'simulationUnchangedByAudioControls':True,'errors':errors,'finalDiagnostics':reset}
    print(json.dumps(report,indent=2),flush=True)
    report.update({
      'generatedAt': datetime.now(timezone.utc).isoformat(),
      'baseCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
      'scope': 'Chrome real-time Web Audio output and desktop/mobile viewport interactions, not subjective listening or other-browser certification.',
      'reproduce': 'python3 frontend/scripts/audio_qa.py --full-cycle',
      'fullProgression': cycle,
      'suspendResumeWorks': True,
      'muteShortcutWhileSliderFocused': True,
      'browserVersion': browser.version,
      'sourceHashes': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((ROOT / 'frontend/src').rglob('*')) if path.suffix in {'.ts', '.tsx', '.css'}},
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    assert not errors
    await browser.close()
asyncio.run(main())
