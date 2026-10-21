#!/usr/bin/env python3
"""Publish a Space Bulletin Weekly episode (weekly, ~5 min, Saturday mornings). Repo/feed URL keep the original space-bulletin-daily name. Usage: python3 publish.py SCRIPT.txt [--date YYYY-MM-DD] [--no-push]"""
import os,sys,re,json,time,html,shutil,subprocess,argparse,datetime,tempfile,urllib.request,urllib.error
from email.utils import format_datetime
from zoneinfo import ZoneInfo
REPO=os.path.dirname(os.path.abspath(__file__))
BASE="https://tiwarishashank.github.io/space-bulletin-daily/"
ENDPOINT="https://westus2.tts.speech.microsoft.com/cognitiveservices/v1"
VOICE=os.environ.get("SPACE_VOICE","en-US-Ava:DragonHDLatestNeural")
KEEP=60
TITLE="Space Bulletin Weekly"
AUTHOR="Space Bulletin Weekly"
SUBTITLE="The week in space news, in about five minutes, every Saturday morning."
DESC=("Space Bulletin Weekly is a roughly five-minute roundup of the week's most important space news, published every Saturday morning. "
      "Each edition covers NASA and the Artemis program, SpaceX, Earth observation, major space deals and funding, and space-tech startups. "
      "Read by an AI-voiced newsreader (synthetic voice); stories are researched from published sources and checked by an AI assistant.")
ORD=["","first","second","third","fourth","fifth","sixth","seventh","eighth","ninth","tenth","eleventh","twelfth","thirteenth","fourteenth","fifteenth","sixteenth","seventeenth","eighteenth","nineteenth","twentieth","twenty-first","twenty-second","twenty-third","twenty-fourth","twenty-fifth","twenty-sixth","twenty-seventh","twenty-eighth","twenty-ninth","thirtieth","thirty-first"]
MONTHS={"jan":"January","feb":"February","mar":"March","apr":"April","may":"May","jun":"June","jul":"July","aug":"August","sep":"September","sept":"September","oct":"October","nov":"November","dec":"December"}
def speak_dates(t):
    """Spell dates out for the voice: 'Oct. 20' / 'October 20th' -> 'October twentieth' (avoids the voice reading '20.' as a decimal)."""
    pat=r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b"
    def f(m):
        n=int(m.group(2))
        if not 1<=n<=31: return m.group(0)
        return MONTHS[m.group(1).lower()[:4] if m.group(1).lower().startswith("sept") else m.group(1).lower()[:3]]+" "+ORD[n]
    return re.sub(pat,f,t)
def sh(*a,**k): return subprocess.run(a,check=True,cwd=REPO,**k)
def ensure_ffmpeg():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        subprocess.run("sudo apt-get update && sudo apt-get install -y ffmpeg",shell=True,check=True)
def chunks(paras,limit=5000):
    out,cur=[],[]
    for p in paras:
        if cur and sum(len(x) for x in cur)+len(p)>limit: out.append(cur); cur=[]
        cur.append(p)
    if cur: out.append(cur)
    return out
def ssml(paras):
    body='<break time="700ms"/>'.join(html.escape(p,quote=False) for p in paras)
    return ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
            f'<voice name="{VOICE}">{body}</voice></speak>')
def tts(text_ssml,out):
    key=os.environ["AZURE_SPEECH_KEY"]
    for i in range(6):
        req=urllib.request.Request(ENDPOINT,data=text_ssml.encode(),method="POST",headers={
            "Ocp-Apim-Subscription-Key":key,"Content-Type":"application/ssml+xml",
            "X-Microsoft-OutputFormat":"audio-24khz-96kbitrate-mono-mp3","User-Agent":"space-bulletin-weekly"})
        try:
            with urllib.request.urlopen(req,timeout=120) as r: open(out,"wb").write(r.read()); return
        except urllib.error.HTTPError as e:
            if e.code==429 or e.code>=500:
                time.sleep(int(e.headers.get("Retry-After") or 2**i*3)); continue
            raise SystemExit(f"TTS failed HTTP {e.code}: {e.read()[:300]!r}")
        except urllib.error.URLError: time.sleep(2**i*3)
    raise SystemExit("TTS failed after retries")
def duration(p):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p]).strip())
JINGLE=os.path.join(REPO,"jingle.mp3")
OVERLAP=0.3
OUTRO_GAP=0.6
MIN_SEC=280  # 4:40
MAX_SEC=315  # 5:15
def add_jingle(voice,jingle,out,overlap=OVERLAP):
    """Jingle at the start (crossfaded into the voice) and again at the end after a short pause; loudness-normalize to -16 LUFS."""
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i",jingle,"-i",voice,"-filter_complex",
        f"[0:a]aresample=44100,aformat=channel_layouts=mono,asplit=2[j][j2];[1:a]aresample=44100,aformat=channel_layouts=mono[v];"
        f"[j][v]acrossfade=d={overlap}:c1=tri:c2=tri[a];anullsrc=r=44100:cl=mono,atrim=0:{OUTRO_GAP}[s];"
        f"[a][s][j2]concat=n=3:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11[o]",
        "-map","[o]","-ar","44100","-ac","1","-b:a","96k",out],check=True)
def hms(s): s=int(round(s)); return f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"
def x(s): return html.escape(s,quote=True)
def build_feed(eps):
    now=format_datetime(datetime.datetime.now(datetime.timezone.utc))
    items=[]
    for e in eps:
        items.append(f"""  <item>
    <title>{x(e['title'])}</title>
    <description>{x(e['description'])}</description>
    <itunes:summary>{x(e['description'])}</itunes:summary>
    <guid isPermaLink="false">space-bulletin-daily-{e['date']}</guid>
    <pubDate>{e['pubDate']}</pubDate>
    <enclosure url="{BASE}episodes/{e['date']}.mp3" length="{e['length']}" type="audio/mpeg"/>
    <itunes:duration>{e['duration']}</itunes:duration>
    <itunes:episodeType>full</itunes:episodeType>
    <itunes:explicit>false</itunes:explicit>
  </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:podcast="https://podcastindex.org/namespace/1.0">
<channel>
  <title>{x(TITLE)}</title>
  <link>{BASE}</link>
  <atom:link href="{BASE}feed.xml" rel="self" type="application/rss+xml"/>
  <description>{x(DESC)}</description>
  <itunes:summary>{x(DESC)}</itunes:summary>
  <itunes:subtitle>{x(SUBTITLE)}</itunes:subtitle>
  <podcast:updateFrequency rrule="FREQ=WEEKLY;BYDAY=SA">Weekly</podcast:updateFrequency>
  <language>en-us</language>
  <copyright>© {datetime.date.today().year} Shashank Tiwari</copyright>
  <lastBuildDate>{now}</lastBuildDate>
  <itunes:author>{x(AUTHOR)}</itunes:author>
  <itunes:owner><itunes:name>{x(AUTHOR)}</itunes:name><itunes:email>shashank.iitb@gmail.com</itunes:email></itunes:owner>
  <itunes:image href="{BASE}cover-weekly.jpg"/>
  <image><url>{BASE}cover-weekly.jpg</url><title>{x(TITLE)}</title><link>{BASE}</link></image>
  <itunes:category text="Science"><itunes:category text="Astronomy"/></itunes:category>
  <itunes:explicit>false</itunes:explicit>
  <itunes:type>episodic</itunes:type>
{chr(10).join(items)}
</channel>
</rss>
"""
def git_net(*args,attempts=5,timeout=120):
    """Run a networked git command with a timeout and retries (backoff 30/60/120/240s)."""
    waits=[30,60,120,240]
    for i in range(attempts):
        try:
            r=subprocess.run(["git",*args],cwd=REPO,timeout=timeout)
            if r.returncode==0: return
            why=f"exit {r.returncode}"
        except subprocess.TimeoutExpired: why=f"timed out after {timeout}s"
        if i<attempts-1:
            w=waits[min(i,len(waits)-1)]
            print(f"git {' '.join(args)} failed ({why}); retry {i+2}/{attempts} in {w}s",file=sys.stderr); time.sleep(w)
    raise SystemExit(f"ERROR: git {' '.join(args)} failed after {attempts} attempts ({why}); episode built locally but NOT published")
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("script"); ap.add_argument("--date"); ap.add_argument("--no-push",action="store_true"); ap.add_argument("--voice")
    a=ap.parse_args()
    global VOICE
    if a.voice: VOICE=a.voice
    ensure_ffmpeg()
    date=a.date or datetime.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
    d=datetime.date.fromisoformat(date)
    text=open(a.script,encoding="utf-8").read()
    paras=[re.sub(r"\s+"," ",p).strip() for p in re.split(r"\n\s*\n",text) if p.strip()]
    if len(paras)<=1: paras=[l.strip() for l in text.splitlines() if l.strip()]
    paras=[speak_dates(p) for p in paras]
    os.makedirs(f"{REPO}/episodes",exist_ok=True); os.makedirs(f"{REPO}/scripts",exist_ok=True)
    mp3=f"{REPO}/episodes/{date}.mp3"
    with tempfile.TemporaryDirectory() as td:
        parts=[]
        for i,c in enumerate(chunks(paras)):
            p=f"{td}/p{i}.mp3"; tts(ssml(c),p); parts.append(p)
        if len(parts)==1: shutil.copy(parts[0],mp3)
        else:
            open(f"{td}/l.txt","w").write("".join(f"file '{p}'\n" for p in parts))
            subprocess.run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",f"{td}/l.txt","-c","copy",mp3],check=True)
        if os.path.exists(JINGLE):
            v=f"{td}/voice.mp3"; shutil.move(mp3,v); add_jingle(v,JINGLE,mp3); print("jingle added")
    dur=duration(mp3)
    if dur<MIN_SEC or dur>MAX_SEC:
        bar="!"*70
        how="trim" if dur>MAX_SEC else "lengthen"
        print(f"{bar}\nWARNING: episode is {dur:.1f}s ({hms(dur)}), outside the 4:40-5:15 window; {how} the script next time (target about 5:00)\n{bar}",file=sys.stderr)
    else: print(f"duration {dur:.1f}s")
    sp=f"{REPO}/scripts/{date}.txt"
    if os.path.abspath(a.script)!=os.path.abspath(sp): shutil.copy(a.script,sp)
    mf=f"{REPO}/episodes.json"
    eps=json.load(open(mf)) if os.path.exists(mf) else []
    eps=[e for e in eps if e["date"]!=date]
    pub=datetime.datetime.combine(d,datetime.time(6,47),ZoneInfo("America/Los_Angeles"))
    summary=paras[1] if len(paras)>1 else paras[0]
    eps.append({"date":date,"title":f"Space Bulletin Weekly – {d.strftime('%A, %B')} {d.day}, {d.year}",
        "description":(summary[:400]+("…" if len(summary)>400 else "")),
        "pubDate":format_datetime(pub),"length":os.path.getsize(mp3),"duration":hms(duration(mp3))})
    eps.sort(key=lambda e:e["date"],reverse=True)
    keep,old=eps[:KEEP],eps[KEEP:]
    for e in old:
        for f in (f"{REPO}/episodes/{e['date']}.mp3",f"{REPO}/scripts/{e['date']}.txt"):
            if os.path.exists(f): os.remove(f)
    keepd={e["date"] for e in keep}
    for f in os.listdir(f"{REPO}/episodes"):
        if f.endswith(".mp3") and f[:-4] not in keepd: os.remove(f"{REPO}/episodes/{f}")
    json.dump(keep,open(mf,"w"),indent=1,ensure_ascii=False)
    open(f"{REPO}/feed.xml","w",encoding="utf-8").write(build_feed(keep))
    import xml.dom.minidom; xml.dom.minidom.parse(f"{REPO}/feed.xml")
    if not os.path.exists(f"{REPO}/.nojekyll"): open(f"{REPO}/.nojekyll","w").close()
    if a.no_push: print("built",mp3); return
    sh("git","add","-A")
    if subprocess.run(["git","diff","--cached","--quiet"],cwd=REPO).returncode:
        sh("git","commit","-q","-m",f"Episode {date}")
    if subprocess.run(["git","ls-remote","--exit-code","--heads","origin","main"],cwd=REPO,capture_output=True,timeout=120).returncode==0:
        git_net("pull","-q","--rebase","origin","main")
    git_net("push","-q","origin","HEAD:main")
    print("published",BASE+f"episodes/{date}.mp3")
if __name__=="__main__": main()
