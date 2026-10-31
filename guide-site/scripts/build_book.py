from pathlib import Path
from html.parser import HTMLParser
import ast, hashlib, html, json, re, shutil, subprocess
from content import pages, chapters, questions

SITE = Path(__file__).resolve().parents[1]
ROOT = SITE.parent
DIST = SITE / 'dist'
DIST.mkdir(exist_ok=True)
ASSETS = DIST / 'assets'
ASSETS.mkdir(exist_ok=True)

class Plain(HTMLParser):
    def __init__(self): super().__init__(); self.out=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag=='pre': self.skip+=1; self.out.append('\nThe code example is available in the written edition.\n')
        if tag in ('p','h3','li','tr'): self.out.append('\n')
    def handle_endtag(self,tag):
        if tag=='pre': self.skip-=1
        if tag in ('p','h3','li','tr'): self.out.append('\n')
        if tag in ('td','th'): self.out.append('; ')
    def handle_data(self,data):
        if not self.skip: self.out.append(data)
def plain(s):
    parser=Plain(); parser.feed(s)
    return re.sub(r'\n{3,}','\n\n',''.join(parser.out)).strip()

special = {
 'backend/ppo_service.py':'Loads verified actor modules; supplies session-free setup previews and owns missions, recurrent state and idempotent steps.',
 'scripts/swarm.mjs':'Checks prerequisites, reuses healthy services and starts the local frontend, PPO backend and audiobook.',
 'simulation/ros2_ws/src/swarm_sar_control/swarm_sar_control/slam_agent.py':'Connects per-rover SLAM maps and estimated TF poses to mission-frame belief, peer snapshots and health telemetry.',
 'simulation/ros2_ws/src/swarm_sar_control/swarm_sar_control/slam_support.py':'ROS-independent map projection, snapshot recovery, admission, byte budgeting and leased frontier intent.',
 'frontend/src/observatory/ObservatoryScene.tsx':'Renders measured occupancy, robots, paths and actual packet arcs with Three.js.',
 'simulation/src/swarm_sar/sim/env.py':'PettingZoo ParallelEnv: seven-action interface, private observations, local routes, safety and peer exchange.',
 'simulation/src/swarm_sar/sim/engine.py':'Deterministic truth-world stepping, simultaneous movement, battery, sensors and metrics.',
 'simulation/src/swarm_sar/learning/training.py':'Constructs RLlib PPO and maps rover/drone agents to two shared policies.',
 'simulation/src/swarm_sar/learning/env.py':'RLlib adapter with variable teams, seeded domain randomization and shared team reward.',
 'simulation/src/swarm_sar/learning/observation.py':'Encodes and bounds the local policy vector and separate action mask.',
 'simulation/src/swarm_sar/learning/rllib_module.py':'Custom PPO module that applies the action mask in training and inference.',
 'simulation/src/swarm_sar/policy_contract.py':'Versioned gpu-v1 input/action semantics and canonical contract hash.',
 'simulation/src/swarm_sar/learning/inference.py':'Policy forward passes, optional seeded sampling and individual recurrent state.',
 'simulation/src/swarm_sar/learning/demonstrations.py':'Policy-compatible decentralized expert, chunk writer and dataset validation.',
 'simulation/src/swarm_sar/learning/behavior_cloning.py':'Recurrent weighted supervised imitation with seed splits, sequence windows and burn-in.',
 'simulation/src/swarm_sar/baselines/frontier.py':'Coordinated frontier reference with reservation table and evidence board.',
 'simulation/src/swarm_sar/baselines/decentralized.py':'Private agent loops, peer claims, rendezvous branch ownership and investigation.',
 'simulation/src/swarm_sar/sensing/victim_sensor.py':'Synthetic noisy thermal/acoustic readings and range/LOS survivor confirmation.',
 'simulation/src/swarm_sar/network/peer.py':'Range/wall/loss/delay/bandwidth/TTL/partition packet transport.',
 'simulation/src/swarm_sar/mapping/topology.py':'NetworkX private graph updates and topology export; no GNN.',
 'frontend/src/store/simStore.ts':'Zustand state for mission controls, UI settings and selected engine ownership.',
 'frontend/src/ppo/PPOBridge.tsx':'Manages remote mission requests, pause/reset, errors and response ordering.',
 'frontend/src/ppo/RemoteEngine.ts':'Adapts Python snapshots to the rendering interface without local simulation ticks.',
 'frontend/src/simulation/core/SimulationEngine.ts':'Browser heuristic simulation lifecycle, decisions, motion and telemetry.',
 'frontend/src/simulation/controller/DecentralizedController.ts':'Browser local-view heuristic choices, local goals and peer coordination.',
 'frontend/src/components/MazeEditor.tsx':'Interactive terrain strokes, undo/redo and validated layout save.',
 'frontend/src/presentation/survivorStories.ts':'Authored fictional discovery narratives used for the UI.',
 'models/ppo_754k/ppo_754k_review.json':'Full development cohort review and paired references for the selected checkpoint.',
 'models/ppo_754k/training_definition.json':'Effective selected run definition, including the 16-runner override.',
 'docs/project_report.md':'Current integrated capability assessment, scoped evidence, limits and later changes.',
 'docs/gallery.md':'Real capture descriptions and the provenance limits of browser, PPO and ROS media.',
}
def purpose(path, text, doc):
    if path in special: return special[path]
    if doc: return doc.split('\n\n')[0].replace('\n',' ')[:260]
    name=Path(path).name; readable=Path(path).stem.replace('_',' ').replace('-',' ')
    if '/checkpoint/' in path: return 'Historical Step 3 checkpoint artifact: '+readable+'. Stored for provenance; not executed by this reader.'
    if name.startswith('test_') or '.test.' in name: return 'Automated checks for '+readable.replace('test','').strip()+'. Inspect the source for assertions and validation scope.'
    if path.endswith('.npz'): return 'Compressed expert demonstration chunk. Its integrity and row layout are defined by the dataset manifest.'
    if path.endswith(('.png','.gif','.jpg','.jpeg')): return 'Original project visual artifact. See the containing capture manifest or gallery for its runtime and provenance.'
    if path.endswith(('.pkl','.pt','.pth')): return 'Serialized model/runtime state. Catalogued as binary metadata; not opened or executed in the book.'
    if path.endswith(('.tar.gz','.zip')): return 'Archived model or evidence package. Consult its checksum, manifest and README before use.'
    if path.endswith(('.yaml','.yml')): return 'Configuration for '+readable+'. Effective run overrides may differ from these defaults.'
    if name=='package.xml': return 'ROS package metadata and build/runtime dependencies for '+str(Path(path).parent.name)+'.'
    if name=='CMakeLists.txt': return 'ROS build and install rules for '+str(Path(path).parent.name)+'.'
    if name.endswith('.msg'): return 'Typed ROS message schema: '+readable+'.'
    if name.endswith(('.xacro','.sdf','.world')): return 'Physical simulation description for '+readable+': links, geometry, scene or plugin parameters.'
    if path.startswith('docs/') and path.endswith('.json'): return 'Recorded '+readable+' data. Consult its fields and parent guide for experiment scope.'
    if path.endswith('.md'):
        heading=re.search(r'^#\s+(.+)',text,re.M)
        return 'Documentation: '+(heading.group(1) if heading else readable)+'. Read dates and limits alongside current executable code.'
    if path.endswith('.json'): return 'Structured '+readable+' metadata, configuration or recorded evidence.'
    if '/components/' in path: return 'React interface component for '+readable+'.'
    if '/scene/' in path: return 'Three.js/React scene presentation for '+readable+'.'
    if '/audio/' in path: return 'Browser mission sound implementation: '+readable+'.'
    if path.endswith('__init__.py'): return 'Python package boundary and public imports for '+str(Path(path).parent.name)+'.'
    return readable.capitalize()+' — '+('project tooling or configuration.' if not path.endswith(('.py','.ts','.tsx')) else 'implementation; inspect its declarations and source below.')

files=[]
tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
extensions={'.py','.ts','.tsx','.css','.html','.json','.md','.yaml','.yml','.toml','.txt','.xml','.msg','.xacro','.world','.sdf','.config','.rviz','.sh','.cfg','.sha256','.mjs'}
# Never copy generated reader source back into its own atlas.
shutil.rmtree(DIST/'source', ignore_errors=True)
for path in filter(None,tracked):
    if path.startswith('guide-site/'):
        continue
    full=ROOT/path
    if not full.is_file(): continue
    raw=full.read_bytes(); text=''; declarations=[]; doc=''
    readable=(full.suffix in extensions or full.name in ('CMakeLists.txt','.gitignore','.gitattributes')) and len(raw)<2_500_000
    if readable:
        try: text=raw.decode('utf-8')
        except UnicodeDecodeError: readable=False
    if path.endswith('.py') and readable:
        try:
            tree=ast.parse(text); doc=ast.get_docstring(tree) or ''
            declarations=[dict(name=n.name,line=n.lineno,kind=type(n).__name__) for n in ast.walk(tree) if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef))]
        except SyntaxError: pass
    elif path.endswith(('.ts','.tsx')) and readable:
        declarations=[dict(name=m.group(1),line=text[:m.start()].count('\n')+1,kind='declaration') for m in re.finditer(r'(?:export\s+)?(?:class|function|interface|type)\s+(\w+)',text)]
    url=None
    if readable:
        dest=DIST/'source'/(path+'.txt'); dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text(text)
        url='source/'+path+'.txt'
    files.append(dict(path=path,size=len(raw),readable=readable,url=url,purpose=purpose(path,text,doc),declarations=declarations[:100],sha256=hashlib.sha256(raw).hexdigest(),category=path.split('/')[0] if '/' in path else 'root',lines=text.count('\n')+1 if readable else None))

for f in ['office-overview.png','office-fleet.png','mine-team.png','apartment-team.png','ppo-completed.png','mission-live.gif']:
    shutil.copy2(ROOT/'docs/media/frontend'/f,ASSETS/f)
for f in ['03-gazebo-overview.png','07-gazebo-top.png','10-rviz-progress.png']:
    shutil.copy2(ROOT/'docs/media/simulation-screenshots'/f,ASSETS/f)
for f in ['ppo_754k_seed10000.gif','rviz-map-sequence.gif']:
    shutil.copy2(ROOT/'docs/media'/f,ASSETS/f)

for source in (ROOT/'docs/media/updates').glob('*.png'):
    shutil.copy2(source, ASSETS/source.name)

for i,page in enumerate(pages):
    page['id']=i
    page['text']=plain(page['body']+'\n'+page['notes'])
    page['words']=len(page['text'].split())
    page['narration']=page['title']+'.\n'+page['deck']+'\n\n'+page['text']
    page['audio']='audio/page-'+str(i+1).zfill(3)+'.m4a'

revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
data=dict(title='SWARM SAR — The Fieldbook',edition='31 October 2026',revision=revision,chapters=[dict(id=i,title=c[0],subtitle=c[1],start=next(j for j,p in enumerate(pages) if p['chapter']==i)) for i,c in enumerate(chapters)],pages=pages,questions=questions,files=files,wordCount=sum(p['words'] for p in pages))
(DIST/'book.json').write_text(json.dumps(data,ensure_ascii=False))
transcript='SWARM SAR — THE FIELDBOOK\nOm Rashiya · Yash Bharvada · Purva Shah · Pankti Akbari\nEdition: 31 October 2026\nSource revision: '+revision+'\n\n'
for page in pages:
    transcript+='\n'+'='*70+'\nPAGE '+str(page['id']+1)+' · '+chapters[page['chapter']][0].upper()+'\n'+page['title']+'\n'+page['deck']+'\n\n'+page['text']+'\n\nCode examples / written reference:\n'+plain(re.sub(r'<pre>.*?</pre>','',page['body']+page['notes'],flags=re.S))[:0]
    examples=re.findall(r'<pre><code>(.*?)</code></pre>',page['body']+page['notes'],re.S)
    transcript+='\n'.join(html.unescape(s) for s in examples)+'\nSources: '+'; '.join(page['sources'])+'\n'
(DIST/'swarm-sar-fieldbook.txt').write_text(transcript)
(DIST/'file-atlas.json').write_text(json.dumps(files,ensure_ascii=False,indent=2))
(SITE/'narration.json').write_text(json.dumps([dict(id=p['id'],title=p['title'],chapter=p['chapter'],text=p['narration']) for p in pages],ensure_ascii=False))
print(json.dumps(dict(pages=len(pages),chapters=len(chapters),words=data['wordCount'],files=len(files),readableFiles=sum(f['readable'] for f in files),revision=revision)))
