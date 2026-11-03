"""DENGAR AI v9 - five linked dashboards in a 16:9 widescreen interface.

Keep executive.py, operations.py, user_behavior.py, citizen_voice.py,
and citizen_issue_intelligence.py in the same directory as this file.

Usage:
  python dashboard_v9.py --input "output data/analyzed(1).csv"
  python dashboard_v9.py --input "output data/analyzed(1).csv" --no-open

Produces dashboard_v9.html and five corresponding local HTML files.
Each page retains its own filters, including Further Investigation.
Requires: pandas, plotly.
"""
from pathlib import Path
import argparse
import subprocess
import sys
import webbrowser
from html import escape

PAGES = [
    ('Executive Overview','executive.py','dengar_executive_v9.html'),
    ('Kiosk Operations','operations.py','dengar_operations_v9.html'),
    ('User Behaviour','user_behavior.py','dengar_user_behavior_v9.html'),
    ('Citizen Voice','citizen_voice.py','dengar_citizen_voice_v9.html'),
    ('Citizen Issue Intelligence','citizen_issue_intelligence.py','dengar_citizen_issue_intelligence_v9.html'),
]


def build(input_csv, destination):
    folder = Path(destination).resolve().parent
    folder.mkdir(parents=True, exist_ok=True)
    script_dir = Path(__file__).resolve().parent
    source = Path(input_csv).resolve()
    if not source.is_file():
        raise FileNotFoundError(f'Missing analyzed CSV: {source}')
    for title, script, html_name in PAGES:
        script_path = script_dir / script
        if not script_path.exists():
            raise FileNotFoundError(f'Missing component: {script_path}. Keep all six .py files together.')
        command = [sys.executable, str(script_path),'--input',str(source),'--output',str(folder/html_name),'--no-open']
        print('Generating:',title,flush=True)
        subprocess.run(command,check=True)
    tabs='\n'.join(f'<button type="button" data-id="{i}" class="{"active" if i==0 else ""}" onclick="switchTo({i})">{escape(title)}</button>' for i,(title,_,_) in enumerate(PAGES))
    frames='\n'.join(f'<iframe title="{escape(title)}" id="frame-{i}" src="{escape(html_name)}" loading="{ "eager" if i==0 else "lazy" }" style="display:{"block" if i==0 else "none"}" referrerpolicy="no-referrer"></iframe>' for i,(title,_,html_name) in enumerate(PAGES))
    page=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DENGAR AI | Unified Intelligence v9</title>
<style>*{{box-sizing:border-box}}html,body{{margin:0;height:100%;background:#e8ecf4;font:13px Inter,'Segoe UI',Arial,sans-serif;color:#e6edfb}}.app{{display:flex;flex-direction:column;width:100%;height:100dvh;min-height:500px}}nav{{display:flex;align-items:center;gap:5px;background:#101f4b;padding:9px 14px;flex-wrap:wrap;box-shadow:0 2px 12px #10204822;z-index:2}}nav strong{{font-size:16px;margin-right:18px;white-space:nowrap}}nav strong span{{color:#f6cc4b}}nav button{{color:#c8d5ed;background:transparent;border:1px solid transparent;border-radius:8px;cursor:pointer;padding:10px 11px;font:inherit;font-size:12px;white-space:nowrap}}nav button.active,nav button:hover{{background:#eef3ff;color:#1b3063}}.stage{{flex:1;min-height:0;width:100%;background:#edf1f7}}iframe{{border:0;width:100%;height:100%}}.stage:fullscreen{{width:100vw;height:100vh}}.right{{margin-left:auto}}#full{{border:1px solid #62749f}}@media(max-width:900px){{nav{{padding:7px;gap:3px}}nav strong{{width:100%}}nav button{{font-size:11px;padding:7px}}}}</style></head><body><div class="app"><nav><strong>DENGAR<span>Â·</span>AI <small style="font-size:10px;font-weight:400">V9</small></strong>{tabs}<button class="right" id="full" onclick="toggleFull()">Widescreen / Fullscreen</button></nav><div class="stage" id="stage">{frames}</div></div>
<script>function switchTo(n){{document.querySelectorAll('[data-id]').forEach(x=>x.classList.toggle('active',Number(x.dataset.id)===n));document.querySelectorAll('iframe').forEach((x,i)=>{{x.style.display=i===n?'block':'none';if(i===n&&x.contentWindow){{try{{x.contentWindow.dispatchEvent(new Event('resize'))}}catch(e){{}}}}}})}}function toggleFull(){{let s=document.getElementById('stage');if(!document.fullscreenElement){{s.requestFullscreen?.()}}else{{document.exitFullscreen?.()}}}}</script></body></html>'''
    dest=Path(destination).resolve()
    dest.write_text(page,encoding='utf-8')
    return dest


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',default='output data/analyzed.csv')
    ap.add_argument('--output',default='dashboard_v9.html')
    ap.add_argument('--no-open',action='store_true')
    args=ap.parse_args()
    src=Path(args.input)
    if not src.is_file() and args.input=='output data/analyzed.csv':
        for p in ['analyzed.csv','analyzed(1).csv','output data/analyzed(1).csv']:
            if Path(p).is_file():src=Path(p);break
    dest=build(src,args.output)
    print('Combined dashboard:',dest)
    if not args.no_open:webbrowser.open(dest.as_uri())

if __name__=='__main__':main()

