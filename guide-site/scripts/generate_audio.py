"""Generate genuine static English audio and a chaptered M4B with local macOS TTS."""
from pathlib import Path
import concurrent.futures, hashlib, json, re, subprocess, tempfile
SITE=Path(__file__).resolve().parents[1]
items=json.loads((SITE/'narration.json').read_text())
OUT=SITE/'dist/audio'; OUT.mkdir(exist_ok=True)
def speech(text):
    replacements={'PPO':'P P O','MAPPO':'map P O','MARL':'multi-agent reinforcement learning','RLlib':'Ray R L lib','ROS 2':'Ross two','RViz':'R viz','LSTM':'L S T M','GAE':'G A E','BC':'behavior cloning','GPU':'G P U','CPU':'C P U','GNN':'G N N','SLAM':'slam','TTL':'time to live','HTTP':'H T T P','API':'A P I','TF':'T F','UI':'user interface','×':' by ','→':' to ','−':' minus ','≈':' approximately ','π':' pi ','γ':' gamma ','λ':' lambda ','δ':' delta '}
    for a,b in sorted(replacements.items(),key=lambda x:-len(x[0])):
        text=re.sub(r'(?<![A-Za-z])'+re.escape(a)+r'(?![A-Za-z])',lambda m:b,text)
    return text
def run(item):
    target=OUT/f"page-{item['id']+1:03d}.m4a"; spoken=speech(item['text']); identity=hashlib.sha256(spoken.encode()).hexdigest(); marker=target.with_suffix('.sha256')
    if not(target.exists() and marker.exists() and marker.read_text()==identity):
        with tempfile.TemporaryDirectory(prefix='swarm-narration-') as tmp:
            txt=Path(tmp)/'text.txt'; aiff=Path(tmp)/'voice.aiff'; txt.write_text(spoken)
            subprocess.run(['/usr/bin/say','-v','Samantha','-r','165','-f',str(txt),'-o',str(aiff)],check=True,capture_output=True)
            subprocess.run(['/opt/homebrew/bin/ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(aiff),'-c:a','aac','-b:a','40k','-movflags','+faststart',str(target)],check=True,capture_output=True)
        marker.write_text(identity)
    duration=float(subprocess.check_output(['/opt/homebrew/bin/ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(target)]).decode())
    return dict(id=item['id'],duration=duration,file=target.name)
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for result in pool.map(run,items):
        results.append(result)
        if len(results)%10==0: print(f"Narrated {len(results)}/{len(items)} pages",flush=True)
results.sort(key=lambda x:x['id'])
book=json.loads((SITE/'dist/book.json').read_text())
for result in results: book['pages'][result['id']]['duration']=result['duration']
book['audioDuration']=sum(r['duration'] for r in results)
(SITE/'dist/book.json').write_text(json.dumps(book,ensure_ascii=False))
(OUT/'manifest.json').write_text(json.dumps(dict(voice='Samantha',language='en-US',method='macOS system text-to-speech',rate=165,tracks=results,totalDuration=book['audioDuration']),indent=2))
with tempfile.TemporaryDirectory(prefix='swarm-m4b-') as tmp:
    listing=Path(tmp)/'tracks.txt'; listing.write_text(''.join("file '"+str(OUT/r['file'])+"'\n" for r in results))
    elapsed=0; meta=';FFMETADATA1\ntitle=SWARM SAR — The Fieldbook\nartist=Om Rashiya, Yash Bharvada, Purva Shah, Pankti Akbari\ncomment=Synthetic English narration of the repository-grounded fieldbook.\n'
    for item,result in zip(items,results):
        end=elapsed+round(result['duration']*1000)
        meta+=f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={elapsed}\nEND={end}\ntitle={item['id']+1:02d}. {item['title']}\n"; elapsed=end
    metadata=Path(tmp)/'metadata.txt'; metadata.write_text(meta)
    subprocess.run(['/opt/homebrew/bin/ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),'-i',str(metadata),'-map_metadata','1','-map_chapters','1','-c:a','aac','-b:a','32k','-movflags','+faststart',str(SITE/'dist/swarm-sar-fieldbook.m4b')],check=True)
print(json.dumps(dict(tracks=len(results),minutes=round(book['audioDuration']/60,1),audiobookBytes=(SITE/'dist/swarm-sar-fieldbook.m4b').stat().st_size)),flush=True)
