"""DENGAR AI - Citizen Issue Intelligence, standalone dashboard.

Run:
    python citizen_issue_intelligence.py --input "output data/analyzed(1).csv"
    python citizen_issue_intelligence.py --input "output data/analyzed(1).csv" --no-open
Requires: pip install pandas plotly
Output: dengar_citizen_issue_intelligence.html (self-contained, works offline).

Five ministry scoring dimensions are presented as model assessments, not verified cases.
Non-numeric statuses NE / IE / unavailable are never interpreted as scores of zero.
"""
from pathlib import Path
import argparse
import json
import webbrowser
import pandas as pd
from plotly.offline import get_plotlyjs

TOPICS={"POL":"Policing & community safety","IMM":"Immigration & borders","JPN":"MyKad & civil registration","CYB":"Scams & cybercrime","FWK":"Foreign workers","GFB":"Government feedback","OTH":"Other ministry matters"}
DIMS={"clarity":"Issue clarity","evidence":"Evidence strength","impact":"Impact severity","action":"Request actionability","urgency":"Urgency"}
SOURCE_DIMS={"clarity":"issue_clarity","evidence":"evidence_strength","impact":"impact_severity","action":"request_actionability","urgency":"urgency"}

def get(df,*names,default=None):
    for name in names:
        if name in df.columns:return df[name]
    return pd.Series(default,index=df.index)

def num(v):
    try:
        n=float(v)
        return round(n,3) if 1<=n<=5 and pd.notna(n) else None
    except (TypeError,ValueError):return None

def flag(v):return str(v).strip().lower() in ('true','1','yes','y')

def text(v,default=''):
    if isinstance(v,(dict,list)):return json.dumps(v,ensure_ascii=False)
    try:
        if pd.isna(v):return default
    except (ValueError,TypeError):pass
    return str(v).strip()

def prepare(df):
    if 'session_id' not in df:raise ValueError('Missing session_id column. Use the fully scored analyzed CSV.')
    data=df.copy()
    src=get(data,'dataset_source','dataset','source',default='Unknown').fillna('Unknown').astype(str)
    data['_source']=src.map(lambda s:'SP1' if 'sp1' in s.lower() else 'SP9' if 'sp9' in s.lower() else s)
    data=data.drop_duplicates(['_source','session_id']).reset_index(drop=True)
    date=pd.to_datetime(get(data,'started_at',default=None),errors='coerce',utc=True).dt.tz_convert('Asia/Kuala_Lumpur')
    result=[]
    for i,r in data.iterrows():
        d=date.iloc[i]
        count=pd.to_numeric(r.get('nonempty_user_message_count',0),errors='coerce')
        responded=flag(r.get('has_user_response',False)) or (pd.notna(count) and count>0)
        p=text(r.get('ministry_topic_code','')).upper()
        a=text(r.get('ai_validated_topic_code','')).upper()
        topic=p if p in TOPICS else a if a in TOPICS else 'UNASSIGNED'
        origin='Primary' if p in TOPICS else 'Scoring-derived' if a in TOPICS else 'Unassigned'
        dims={};status={};reasons={};coverage={}
        for short,long in SOURCE_DIMS.items():
            dims[short]=num(r.get('ai_'+long+'_score'))
            status[short]=text(r.get('ai_'+long+'_status','Unavailable'),'Unavailable') or 'Unavailable'
            reasons[short]=text(r.get('ai_'+long+'_reason',''))[:1800]
            c=r.get('ai_'+long+'_coverage')
            try:coverage[short]=round(float(c),3) if pd.notna(c) else None
            except (ValueError,TypeError):coverage[short]=None
        route=text(r.get('ai_urgency_route',r.get('ai_calc_urgency_route','')))
        if not route or route.lower()=='nan':route='Unavailable'
        s=text(r.get('session_sentiment','unavailable')).lower()
        if not responded or s not in ('negative','neutral','positive','mixed'):s='unavailable'
        intent=text(r.get('intent','needs_review')).lower()
        if not responded:intent='no_response'
        result.append({'id':text(r.get('session_id')),'source':text(r.get('_source')),'date':d.strftime('%Y-%m-%d') if pd.notna(d) else '',
          'datetime':d.isoformat() if pd.notna(d) else '', 'responded':bool(responded),
          'topic':topic,'topicOrigin':origin,'sent':s,'intent':intent,'route':route,
          'scores':dims,'statuses':status,'reasons':reasons,'coverage':coverage,
          'humanReview':flag(r.get('ai_human_review_required',False)),'coverageAudit':flag(r.get('ai_coverage_audit_required',False)),
          'principal':text(r.get('ai_principal_issue',''))[:450],
          'userText':text(r.get('session_user_text',''))[:4000] if responded else '',
          'scoreFull':text(r.get('ai_scoring_full_json',''))[:40000],
          'urgencyReason':text(r.get('ai_urgency_reason',''))[:1800],
          'msgs':int(count) if pd.notna(count) and count>=0 else 0})
    return result

CSS=r'''
:root{--navy:#17295f;--ink:#253754;--muted:#74829a;--line:#e2e8f1;--bg:#f1f4f9;--green:#15936b;--red:#d75a6a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font:12px/1.5 Inter,'Segoe UI',Arial,sans-serif;color:var(--ink)}
header{position:sticky;top:0;z-index:12;padding:11px 24px;background:var(--navy);color:white;display:flex;justify-content:space-between;gap:10px;align-items:center}header strong{font-size:16px}header small{font-size:10px;color:#d2def3}
.shell{max-width:1540px;margin:auto;padding:12px 20px 22px}.toolbar{position:sticky;top:47px;z-index:11;display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:9px;background:#fff;border:1px solid var(--line);border-radius:10px;margin-bottom:11px;box-shadow:0 2px 7px #17295f0b}
.toolbar label{font-size:10px;color:var(--muted)}select,input,button{font-family:inherit}select,input{border:1px solid #d8e1ee;border-radius:7px;padding:6px;color:var(--ink);background:#fff;font-size:11px;max-width:200px}.toolbar button{border:1px solid #d8e1ee;border-radius:7px;padding:7px 11px;background:#fff;cursor:pointer;font-size:11px}
.topline{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:9px}.topline h1{font-size:19px;margin:0}.topline small{color:var(--muted)}
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px;margin-bottom:10px}.kpi{min-width:0;padding:10px 13px;background:white;border:1px solid var(--line);border-top:3px solid #3f62b1;border-radius:10px}.kpi:nth-child(2){border-top-color:#15936b}.kpi:nth-child(3){border-top-color:#bc9040}.kpi:nth-child(4){border-top-color:#d75a6a}.kpi:nth-child(5){border-top-color:#9563b4}.kpi label{font-size:10px;color:var(--muted);display:block;font-weight:600}.kpi b{font-size:22px;display:block;margin:3px 0}.kpi small{color:var(--muted);font-size:10px}
.charts{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:10px}.panel{background:white;border:1px solid var(--line);border-radius:11px;padding:11px;min-width:0;overflow:hidden}.panel h3{margin:0 0 3px;font-size:12px}.panel p{margin:0 0 7px;font-size:10px;color:var(--muted)}.span7{grid-column:span 7}.span5{grid-column:span 5}.span6{grid-column:span 6}.span12{grid-column:span 12}.chart{height:250px;min-width:0}.flexhead{display:flex;align-items:center;justify-content:space-between;gap:7px}.flexhead select{min-width:130px}.detail{margin-top:10px;background:white;border:1px solid var(--line);border-radius:11px;padding:13px}.detail summary{font-size:13px;font-weight:700;cursor:pointer}.detail .charts{margin-top:12px}
.tablewrap{overflow:auto;max-height:415px}table{width:100%;border-collapse:collapse;font-size:11px}td,th{padding:8px 9px;text-align:left;vertical-align:top;border-bottom:1px solid #e9edf4}th{background:#f6f8fc;position:sticky;top:0;white-space:nowrap}tr[data-key]{cursor:pointer}tr[data-key]:hover{background:#f3f6fc}.pill{display:inline-block;border-radius:5px;background:#edf1f8;padding:2px 6px;font-size:10px}.pill.Urgent,.pill.Critical{background:#fee4e8;color:#b6324b}.pill.Priority{background:#fff0ce;color:#8e6112}.footer{margin:12px 2px;color:var(--muted);font-size:10px}
.shade{position:fixed;inset:0;background:#0e1d39a3;z-index:25;display:none;align-items:center;justify-content:center;padding:18px}.shade.open{display:flex}.modal{width:min(950px,100%);max-height:93vh;overflow:auto;padding:19px 21px;background:white;border-radius:13px}.modalhead{display:flex;justify-content:space-between;gap:12px;align-items:center}.modal h3{margin:0;font-size:16px}.modal h4{margin:16px 0 7px;font-size:12px}.modal p{font-size:12px;line-height:1.65}.modal button{border:1px solid #d2deed;background:#f7f9fd;padding:7px 10px;border-radius:8px;cursor:pointer}.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:13px 0}.fact{border:1px solid #e1e8f2;border-radius:8px;padding:9px;min-width:0;overflow-wrap:anywhere}.fact small{display:block;font-size:10px;color:var(--muted);margin-bottom:4px}.scoregrid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}.scorebox{padding:9px;border:1px solid #e1e8f2;border-radius:8px;min-width:0;overflow-wrap:anywhere}.scorebox small{font-size:10px;color:var(--muted)}.scorebox b{display:block;font-size:17px}.pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fc;padding:12px;border-radius:9px;max-height:250px;overflow:auto}.criteria{margin-top:14px}.criteria details{border:1px solid #dce5f1;border-radius:9px;margin-bottom:7px;padding:10px}.criteria summary{cursor:pointer;font-weight:600}.note{color:var(--muted);font-size:10px}
@media(max-width:970px){.span7,.span5,.span6{grid-column:span 12}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.toolbar{position:static}.facts{grid-template-columns:repeat(2,1fr)}.scoregrid{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){.shell{padding:10px}.topline{align-items:flex-start;flex-direction:column}.facts{grid-template-columns:1fr}}@media print{header,.toolbar,.detail,.shade{display:none!important}.shell{padding:0}.panel{break-inside:avoid}body{background:white}}
'''

CSS += '\n/* V7: 16:9 presentation canvas with proportional, responsive investigation area. */\nhtml{scroll-behavior:smooth}body{min-width:0}.shell{width:min(100%,1600px);max-width:1600px;margin:0 auto;padding:clamp(10px,1.1vw,19px)}.charts{grid-template-columns:repeat(12,minmax(0,1fr))}.chart{height:clamp(210px,22vh,310px)}.kpis{gap:clamp(7px,.7vw,12px)}.panel{min-width:0}.detail[open]{min-height:min(90vh,900px);scroll-margin-top:105px}.detail[open] .chart{height:clamp(245px,27vh,370px)}.detail[open] .tablewrap{max-height:clamp(350px,51vh,620px)}.tablewrap{overflow:auto} @media(min-aspect-ratio:16/9) and (min-width:1100px){.shell{width:min(98vw,calc(94vh * 16 / 9),1600px)}.chart{height:clamp(195px,21vh,300px)}} @media(max-width:950px){.shell{width:100%}}\n'

CSS += "\n/* Power BI-style 16:9 presentation mode: six overview visuals, two rows. */\n@media (min-width: 1100px) {\n  .shell { width: min(99vw, 1900px) !important; max-width: 1900px !important; padding: 7px 13px 12px !important; }\n  header { padding: 6px 18px !important; min-height: 34px; }\n  .toolbar { top: 36px !important; padding: 5px 9px !important; margin-bottom: 6px !important; gap: 5px !important; }\n  .toolbar select,.toolbar input { padding: 4px 6px !important; }\n  .toolbar button { padding: 5px 8px !important; }\n  .topline { margin-bottom: 5px !important; }\n  .topline h1 { font-size: 16px !important; }\n  .kpis { margin-bottom: 6px !important; gap: 7px !important; }\n  .kpi { padding: 5px 10px !important; min-height: 58px; }\n  .kpi label { font-size: 9px !important; }\n  .kpi b { font-size: 18px !important; margin: 0 !important; }\n  .kpi small { font-size: 9px !important; }\n  .charts { grid-template-columns: repeat(12,minmax(0,1fr)) !important; gap: 7px !important; }\n  .charts > .panel.span7,.charts > .panel.span5,.charts > .panel.span6,.charts > .panel.span4 { grid-column: span 4 !important; }\n  .charts > .panel.span12 { grid-column: span 12 !important; }\n  .panel { padding: 8px 9px !important; border-radius: 8px !important; }\n  .panel h3 { font-size: 11px !important; line-height: 1.25; }\n  .panel p { font-size: 9px !important; line-height: 1.25; margin-bottom: 3px !important; }\n  .chart { height: clamp(158px, 26vh, 250px) !important; }\n  .footer { font-size: 9px !important; margin: 5px 0 !important; }\n  .detail { margin-top: 6px !important; padding: 8px 10px !important; }\n  .detail summary { font-size: 11px !important; }\n}\n/* An investigation is its own 16:9 presentation view, not a long web page. */\n@media (min-width: 1100px) {\n  .detail[open] {\n    position: fixed !important;\n    z-index: 1000 !important;\n    top: 50% !important;\n    left: 50% !important;\n    transform: translate(-50%,-50%) !important;\n    width: min(96vw, calc(92dvh * 16 / 9), 1900px) !important;\n    height: min(92dvh, calc(96vw * 9 / 16)) !important;\n    min-height: 0 !important;\n    max-height: none !important;\n    background: #fff !important;\n    border: 2px solid #8aa4d5 !important;\n    box-shadow: 0 0 0 100vmax rgba(12,27,56,.63), 0 20px 60px #15224360 !important;\n    padding: 13px 17px !important;\n    overflow: auto !important;\n    overscroll-behavior: contain;\n  }\n  .detail[open] > summary { position: sticky; top: -13px; z-index: 10; background: #fff; padding: 10px 5px !important; border-bottom: 1px solid #e3eaf3; cursor: pointer; }\n  .detail[open] > summary::after { content: '    ✕ Close'; float: right; color: #2d52a1; font-weight: 700; }\n  .detail[open] .charts > .panel.span6, .detail[open] .charts > .panel.span7, .detail[open] .charts > .panel.span5 { grid-column: span 6 !important; }\n  .detail[open] .chart { height: clamp(200px, 29vh, 330px) !important; }\n  .detail[open] .tablewrap { max-height: clamp(230px, 37vh, 490px) !important; }\n}\n@media (max-width: 1099px) and (min-width: 700px) { .charts > .panel.span7,.charts > .panel.span5,.charts > .panel.span6 { grid-column:span 6 !important; } }\n"

BODY=r'''
<header><div><strong>DENGAR<span style="color:#f4c534">·</span>AI</strong>　 Citizen Issue Intelligence<br><small>Ministry of Home Affairs · Severity, evidence, actionability and routing</small></div><small>Model-generated assessments · Not independently verified</small></header>
<main class="shell">
<div class="toolbar"><label>Kiosk <select id="source"><option value="">All sources</option></select></label><label>Ministry topic <select id="topic"><option value="">All topics</option></select></label><label>Sentiment <select id="sent"><option value="">All sentiments</option></select></label><label>Urgency route <select id="route"><option value="">All routes</option></select></label><label>From <input type="date" id="from"></label><label>To <input type="date" id="to"></label><button id="reset">Reset filters</button><button id="export">Export filtered CSV</button></div>
<div class="topline"><h1>Citizen Issue Intelligence</h1><small id="scope"></small></div>
<div class="kpis" id="kpis"></div>
<div class="charts">
<section class="panel span7"><h3>Which Ministry concerns require priority attention?</h3><p>Topic × model urgency route · Stacked sessions; NE and IE retained separately</p><div class="chart" id="c1"></div></section>
<section class="panel span5"><h3>Are serious issues supported by strong evidence?</h3><p>Impact severity × Evidence strength · Only sessions scored in both dimensions</p><div class="chart" id="c2"></div></section>
<section class="panel span6"><h3>Which citizen requests are ready for action?</h3><p>Issue clarity × Request actionability · Count represented by bubble size; grouped by intent</p><div class="chart" id="c3"></div></section>
<section class="panel span6"><h3>Are negative conversations associated with serious issues?</h3><p>Sentiment × Impact severity level · Number of sessions with valid impact scores</p><div class="chart" id="c4"></div></section>
<section class="panel span6"><h3>Where are potentially important issues missing information?</h3><p>Urgency route × Score availability · Scored versus NE / IE / unavailable</p><div class="chart" id="c5"></div></section>
<section class="panel span6"><h3>Which concerns have the greatest action potential?</h3><p>Paired-score comparison by Ministry topic · Mean impact severity versus request actionability · Scored sessions only</p><div class="chart" id="c6"></div></section>
</div>
<details class="detail"><summary>Further Investigation — Scoring dimensions, scoreability, routing and session evidence</summary>
<div class="charts">
<section class="panel span6"><h3>Five scoring dimensions — level distribution</h3><p>Valid numeric scores only · Score bands are descriptive, not official rubric labels</p><div class="chart" id="d1"></div></section>
<section class="panel span6"><h3>Scoring status by dimension</h3><p>Scored / NE / IE / unavailable · Missing is not zero</p><div class="chart" id="d2"></div></section>
<section class="panel span12"><h3>Urgency routing and human-review flags</h3><p>Routing classifications do not establish verified government escalation or case outcome</p><div class="chart" id="d3" style="height:230px"></div></section>
<section class="panel span12"><div class="flexhead"><div><h3>Session explorer</h3><p>Click any record to see dimension-level rationale and supporting evidence</p></div><select id="detailLimit"><option value="75">75 rows</option><option value="200">200 rows</option><option value="500">500 rows</option></select></div><div class="tablewrap" id="rows"></div></section>
</div></details>
<div class="footer">Scope: responding sessions for analysis. Scoring is model-derived and not human validated. NE / IE / unavailable never treated as numeric zero. No confirmed intervention outcomes are inferred. KDN Ministry topics may be sourced from either the primary classifier or scoring-derived fallback.</div>
</main>
<div class="shade" id="shade" role="dialog" aria-modal="true"><div class="modal"><div class="modalhead"><h3 id="modalTitle">Session evidence</h3><button id="close">Close</button></div><div id="modalBody"></div></div></div>
'''

CSS += r'''
/* V9 legend QA: clean, readable labels without overlaying the chart. */
.panel{position:relative}
.chart-key{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));column-gap:5px;row-gap:4px;align-items:center;min-height:20px;max-height:51px;margin:2px 1px 0;padding:3px 0;font:9px/1.15 'Segoe UI',Arial,sans-serif;color:#52617a;overflow:hidden}
.chart-key-item{display:flex;align-items:center;gap:4px;min-width:0;cursor:pointer;background:none;border:0;padding:0;text-align:left;color:inherit;font:inherit}
.chart-key-item span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block}
.chart-key-dot{width:9px;height:9px;border-radius:2px;flex:none}
.chart-key-item[aria-pressed="false"]{opacity:.38}

'''
CSS += r'''
/* V9 layout QA: give every plot a real plot area and reserve legend space outside Plotly. */
@media(min-width:1100px){
 .charts > .panel{height:clamp(315px,33vh,370px)!important;display:flex;flex-direction:column;min-height:0;overflow:hidden}
 .charts > .panel .chart{height:auto!important;min-height:0!important;flex:1 1 0!important;width:100%!important}
 .charts > .panel .chart-key{flex:0 0 auto;margin:5px 1px 0!important;padding:4px 0 2px!important;max-height:80px!important;min-height:0!important;grid-template-columns:repeat(3,minmax(0,1fr));row-gap:6px;column-gap:8px;overflow:visible!important}
 .charts > .panel .chart-key-item{font-size:10px!important;line-height:1.3!important;min-width:0}
 .charts > .panel .chart-key-item span:last-child{white-space:normal!important;text-overflow:clip!important;overflow-wrap:anywhere;overflow:visible!important}
 .charts > .panel h3{font-size:12px!important;line-height:1.35!important}
 .charts > .panel p{font-size:10px!important;line-height:1.3!important;flex:0 0 auto}
 .detail[open] .charts > .panel{height:auto!important;min-height:330px}
 .detail[open] .charts > .panel .chart{height:clamp(230px,29vh,320px)!important;flex:none!important}
}
@media(max-width:1099px){.chart-key{max-height:none!important;overflow:visible!important}.chart-key-item span:last-child{white-space:normal!important}}
'''
CSS += r'''
/* Final V9 fit: allocate space to plotting, labels and readable legends. */
@media(min-width:1100px){
  .charts>.panel{height:clamp(345px,35.4vh,395px)!important;min-width:0;padding:9px 10px 10px!important}
  .charts>.panel .chart{flex:1 1 0!important;min-height:205px!important;height:auto!important;overflow:hidden}
  .charts>.panel .chart-key{flex:0 0 auto!important;display:grid!important;max-height:67px!important;overflow:visible!important;margin:4px 1px 0!important;padding:3px 0!important;gap:5px 8px!important}
  .charts>.panel .chart-key-item{font-size:10px!important;line-height:1.22!important}
  .charts>.panel h3{font-size:12px!important;margin-bottom:3px!important}
  .charts>.panel p{font-size:10px!important;margin-bottom:4px!important}
  .detail[open] .charts>.panel{height:auto!important;min-height:340px!important}
  .detail[open] .charts>.panel .chart{height:clamp(255px,31vh,345px)!important;flex:none!important}
}
@media(min-width:1100px) and (max-height:850px){
  .charts>.panel{height:clamp(295px,38vh,345px)!important}
  .charts>.panel .chart{min-height:175px!important}
}
'''
JS=r'''
function v9Legend(el,traces,show){
  let existing=el.nextElementSibling;
  if(existing?.classList.contains('chart-key'))existing.remove();
  if(!show||!traces||!traces.some(t=>t.name||t.type==='pie'))return;
  let series=(traces.length===1&&traces[0].type==='pie')
   ?(traces[0].labels||[]).map((label,i)=>({name:label,color:(traces[0].marker?.colors||[])[i]||'#7788aa',index:0,pie:i}))
   :traces.map((t,i)=>({name:String(t.name||''),color:typeof t.marker?.color==='string'?t.marker.color:(t.line?.color||'#7f91ac'),index:i})).filter(x=>x.name);
  if(!series.length)return;
  let leg=document.createElement('div');leg.className='chart-key';leg.setAttribute('aria-label','Chart legend');
  series.forEach(item=>{let btn=document.createElement('button');btn.type='button';btn.className='chart-key-item';btn.title=item.name;btn.setAttribute('aria-pressed','true');
    let dot=document.createElement('span');dot.className='chart-key-dot';dot.style.background=item.color;
    let lbl=document.createElement('span');lbl.textContent=item.name;
    btn.append(dot,lbl);
    if(item.pie===undefined)btn.addEventListener('click',()=>{let active=btn.getAttribute('aria-pressed')!=='false';btn.setAttribute('aria-pressed',String(!active));Plotly.restyle(el,{visible:active?'legendonly':true},[item.index])});
    leg.appendChild(btn);
  });
  el.insertAdjacentElement('afterend',leg);
}

const DATA=__DATA__,TOPICS=__TOPICS__,DIM_NAMES=__DIM_NAMES__;
const $=id=>document.getElementById(id),fmt=x=>Number(x||0).toLocaleString('en-US');
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=(a,b)=>b?100*a/b:0;
const orderedTopics=['POL','IMM','JPN','CYB','FWK','GFB','OTH'];
const routeOrder=['Normal','Priority','Urgent','Critical','IE-Human Review','NE','Unavailable'];
const ROUTECOL={Normal:'#15936b',Priority:'#e4ae40',Urgent:'#df654f',Critical:'#9e2637','IE-Human Review':'#9560ae',NE:'#9baac0',Unavailable:'#dce2eb'};
const SENTCOL={positive:'#15936b',negative:'#d75a6a',neutral:'#a9b4c6',mixed:'#d0a143',unavailable:'#dce2eb'};
const dimKeys=['clarity','evidence','impact','action','urgency'];
function count(arr,f){return arr.filter(f).length}
function grouped(rows,key){const m={};rows.forEach(r=>{let k=typeof key==='function'?key(r):r[key];m[k]=(m[k]||0)+1});return Object.entries(m).sort((a,b)=>b[1]-a[1])}
function filter(){const s=$('source').value,t=$('topic').value,v=$('sent').value,u=$('route').value,from=$('from').value,to=$('to').value;return DATA.filter(r=>(!s||r.source===s)&&(!t||r.topic===t)&&(!v||r.sent===v)&&(!u||r.route===u)&&(!from||r.date>=from)&&(!to||r.date<=to))}
function fill(id,values,format=x=>x){const el=$(id);[...new Set(values)].filter(Boolean).sort().forEach(s=>{let o=document.createElement('option');o.value=s;o.textContent=format(s);el.appendChild(o)})}
fill('source',DATA.map(x=>x.source));fill('topic',DATA.map(x=>x.topic).filter(x=>x!=='UNASSIGNED'),x=>TOPICS[x]||x);fill('sent',DATA.filter(x=>x.responded).map(x=>x.sent));fill('route',DATA.filter(x=>x.responded).map(x=>x.route));
function plot(id,traces,extra={}){let el=$(id);if(!el)return;let base={height:250,paper_bgcolor:'#fff',plot_bgcolor:'#fff',font:{family:'Inter, Segoe UI, Arial',size:10,color:'#61718a'},margin:{l:75,r:15,t:10,b:48},xaxis:{automargin:true,gridcolor:'#ecf0f5',zeroline:false},yaxis:{automargin:true,gridcolor:'#ecf0f5',zeroline:false},showlegend:false,hovermode:'closest'};v9Legend(el,traces,extra.showlegend===true);Plotly.react(el,traces,{...base,...extra,margin:{...base.margin,...(extra.margin||{}),b:Math.min((extra.margin?.b??45),id==='c1'?54:42),t:Math.min((extra.margin?.t??10),10),r:Math.max(12,(extra.margin?.r??base.margin.r))},showlegend:false,height:el.clientHeight||250},{responsive:true,displayModeBar:false});}
function safe(n){return typeof n==='number'&&Number.isFinite(n)}
function band(v){if(!safe(v))return 'Not scored';if(v<2)return '1–<2';if(v<3)return '2–<3';if(v<4)return '3–<4';if(v<4.5)return '4–<4.5';return '4.5–5'}
function status(r,d){if(safe(r.scores[d]))return 'Scored';let t=String(r.statuses[d]||'').toUpperCase();if(t.includes('IE'))return 'IE';if(t.includes('NE'))return 'NE';return 'Unavailable'}
function topicLabel(t){return TOPICS[t]||t}
function noData(id,msg='No matching scored records'){const el=$(id);if(el){Plotly.purge(el);el.innerHTML='<div style="padding:35px 10px;color:#7b879d;text-align:center">'+esc(msg)+'</div>'}}
function render(){let R=filter(),E=R.filter(r=>r.responded),S=E.filter(r=>Object.values(r.scores).some(safe));$('scope').textContent=fmt(R.length)+' sessions · '+fmt(E.length)+' with citizen input';
const urgency=E.filter(r=>['Priority','Urgent','Critical'].includes(r.route)),review=E.filter(r=>r.humanReview),assigned=E.filter(r=>r.topic!=='UNASSIGNED');
const k=[['Responding sessions',E.length,'Citizen input recorded'],['Topics identified',assigned.length,pct(assigned.length,E.length).toFixed(1)+'% of responding sessions'],['Priority / urgent / critical',urgency.length,'Model-routed, not confirmed cases'],['Human-review flags',review.length,'Flagged by scoring pipeline'],['At least one numeric score',S.length,pct(S.length,E.length).toFixed(1)+'% of responding sessions']];
$('kpis').innerHTML=k.map(([a,b,c])=>`<div class="kpi"><label>${esc(a)}</label><b>${fmt(b)}</b><small>${esc(c)}</small></div>`).join('');
// 1. Topic by urgency: stacked horizontal, includes NE and IE.
let T=orderedTopics.filter(t=>assigned.some(r=>r.topic===t));T.sort((a,b)=>count(assigned,r=>r.topic===a)-count(assigned,r=>r.topic===b));
if(T.length){let traces=routeOrder.map(route=>({type:'bar',name:route,x:T.map(topicLabel),y:T.map(t=>count(assigned,r=>r.topic===t&&r.route===route)),marker:{color:ROUTECOL[route]},hovertemplate:'%{x}<br>'+route+': %{y} sessions<extra></extra>'}));plot('c1',traces,{barmode:'stack',showlegend:true,legend:{orientation:'h',x:.5,xanchor:'center',y:1.10,font:{size:9}},margin:{l:45,r:20,t:28,b:88},xaxis:{title:'',tickangle:0,automargin:true,tickfont:{size:9},tickvals:T.map(topicLabel),ticktext:T.map(t=>({FWK:'Foreign<br>workers',JPN:'Civil<br>registration',IMM:'Immigration<br>& borders',POL:'Policing<br>& safety',OTH:'Other KDN<br>matters',GFB:'Government<br>feedback',CYB:'Scams &<br>cybercrime'})[t]||topicLabel(t))},yaxis:{title:'Sessions',rangemode:'tozero'}})}else noData('c1','No assigned Ministry topics in selection');
// 2. severity x evidence, 5x5 discrete heatmap
const both=E.filter(r=>safe(r.scores.impact)&&safe(r.scores.evidence));const bins=['1–<2','2–<3','3–<4','4–<4.5','4.5–5'];
if(both.length){let z=bins.map(impact=>bins.map(evidence=>count(both,r=>band(r.scores.impact)===impact&&band(r.scores.evidence)===evidence)));plot('c2',[{type:'heatmap',x:bins,y:bins,z,colorscale:[[0,'#f1f6fb'],[.25,'#b4d0ec'],[.65,'#4a8ac6'],[1,'#174f96']],showscale:true,hovertemplate:'Impact: %{y}<br>Evidence: %{x}<br>%{z} sessions<extra></extra>',text:z,texttemplate:'%{text}',textfont:{size:10},colorbar:{title:'n',thickness:10}}],{margin:{l:68,r:55,t:8,b:52},xaxis:{title:'Evidence strength'},yaxis:{title:'Impact severity'}})}else noData('c2');
// 3. Actionability vs clarity categorized by intent, bubble size session count.
const viable=E.filter(r=>safe(r.scores.action)&&safe(r.scores.clarity));const validIntent=x=>x&& !['needs_review','unassigned','unavailable','no_response'].includes(x);
if(viable.length){let groupedCells=new Map();viable.forEach(r=>{let intent=validIntent(r.intent)?r.intent:'unclassified';let key=band(r.scores.clarity)+'|'+band(r.scores.action)+'|'+intent;groupedCells.set(key,(groupedCells.get(key)||0)+1)});let groups=[...new Set([...groupedCells.keys()].map(s=>s.split('|')[2]))];let shades=['#3262ac','#149576','#bc8c36','#9565b2','#d65b70','#7589a4'];let traces=groups.map((g,idx)=>{let pts=[...groupedCells].filter(([k])=>k.endsWith('|'+g)).map(([k,n])=>({x:bins.indexOf(k.split('|')[0])+1,y:bins.indexOf(k.split('|')[1])+1,n}));return {type:'scatter',mode:'markers',name:g,x:pts.map(p=>p.x),y:pts.map(p=>p.y),customdata:pts.map(p=>p.n),marker:{size:pts.map(p=>Math.min(37,8+Math.sqrt(p.n)*7)),color:shades[idx%shades.length],opacity:.74,line:{width:1,color:'#fff'}},hovertemplate:g+'<br>Clarity: %{x}<br>Actionability: %{y}<br>%{customdata} sessions<extra></extra>'}});plot('c3',traces,{showlegend:true,legend:{orientation:'h',y:-.37,x:.5,xanchor:'center',entrywidth:115,entrywidthmode:'pixels',font:{size:9}},margin:{l:60,r:8,t:8,b:85},xaxis:{title:'Issue clarity band',tickvals:[1,2,3,4,5],ticktext:bins,range:[.5,5.5],gridcolor:'#edf1f5'},yaxis:{title:'Actionability band',tickvals:[1,2,3,4,5],ticktext:bins,range:[.5,5.5]}})}else noData('c3');
// 4. sentiment by severity: grouped stacked 100% bars (not another bubble).
const imp=E.filter(r=>safe(r.scores.impact)&&r.sent!=='unavailable');const sents=['negative','neutral','positive','mixed'];
if(imp.length){let traces=bins.map((b,i)=>({type:'bar',name:b,x:sents.map(s=>s.charAt(0).toUpperCase()+s.slice(1)),y:sents.map(s=>{let group=imp.filter(r=>r.sent===s);return pct(count(group,r=>band(r.scores.impact)===b),group.length)}),customdata:sents.map(s=>count(imp,r=>r.sent===s&&band(r.scores.impact)===b)),marker:{color:['#d9e3f2','#a5b9d7','#6e97c7','#3e70aa','#193f81'][i]},hovertemplate:'%{x}<br>'+b+': %{y:.1f}%<br>%{customdata} sessions<extra></extra>'}));plot('c4',traces,{barmode:'stack',showlegend:true,legend:{orientation:'h',y:-.29,font:{size:9}},margin:{l:50,r:13,t:7,b:78},yaxis:{title:'Share within sentiment (%)',range:[0,100]}})}else noData('c4');
// 5. coverage: route x dimensions heatmap percent scored, text count n/N
const activeRoutes=routeOrder.filter(route=>E.some(r=>r.route===route));
if(E.length){let z=activeRoutes.map(route=>dimKeys.map(d=>{let a=E.filter(r=>r.route===route);return pct(count(a,r=>status(r,d)==='Scored'),a.length)}));let labels=activeRoutes.map(route=>dimKeys.map(d=>{let a=E.filter(r=>r.route===route);return count(a,r=>status(r,d)==='Scored')+'/'+a.length}));plot('c5',[{type:'heatmap',x:dimKeys.map(d=>DIM_NAMES[d]),y:activeRoutes,z,customdata:labels,zmin:0,zmax:100,colorscale:[[0,'#fce7eb'],[.45,'#efb4a8'],[.51,'#f8f6f1'],[.75,'#a3d8ca'],[1,'#0e7967']],text:labels,texttemplate:'%{text}',textfont:{size:9},hovertemplate:'%{y}<br>%{x}<br>Scored: %{z:.1f}%<br>%{customdata}<extra></extra>',colorbar:{title:'%',thickness:9}}],{margin:{l:110,r:45,t:9,b:65},xaxis:{tickangle:-20},yaxis:{autorange:'reversed'}})}else noData('c5');
// 6. topic average severity vs actionability: per-topic paired scores only, n marker size
const pairs=assigned.filter(r=>safe(r.scores.impact)&&safe(r.scores.action));const cells=orderedTopics.map(topic=>{let a=pairs.filter(r=>r.topic===topic);return {topic,n:a.length,x:a.length?a.reduce((s,r)=>s+r.scores.impact,0)/a.length:0,y:a.length?a.reduce((s,r)=>s+r.scores.action,0)/a.length:0}}).filter(p=>p.n);
if(cells.length){const sorted=[...cells].sort((a,b)=>a.y-b.y);const topics=sorted.map(p=>topicLabel(p.topic));const connectors=sorted.flatMap(p=>[{x:p.x,y:topicLabel(p.topic)},{x:p.y,y:topicLabel(p.topic)},{x:null,y:null}]);plot('c6',[{type:'scatter',mode:'lines',x:connectors.map(p=>p.x),y:connectors.map(p=>p.y),line:{color:'#bbc8d9',width:3},hoverinfo:'skip',showlegend:false},{type:'scatter',mode:'markers',name:'Impact severity',x:sorted.map(p=>p.x),y:topics,marker:{color:'#c58a35',size:11},customdata:sorted.map(p=>p.n),hovertemplate:'%{y}<br>Mean impact: %{x:.2f}/5<br>%{customdata} scored sessions<extra></extra>'},{type:'scatter',mode:'markers',name:'Request actionability',x:sorted.map(p=>p.y),y:topics,marker:{color:'#287eaa',size:11},customdata:sorted.map(p=>p.n),hovertemplate:'%{y}<br>Mean actionability: %{x:.2f}/5<br>%{customdata} scored sessions<extra></extra>'}],{showlegend:true,legend:{orientation:'h',y:-.27,font:{size:9}},margin:{l:155,r:12,t:10,b:80},xaxis:{title:'Average score (1–5)',range:[0.8,5.2],dtick:1},yaxis:{categoryorder:'array',categoryarray:topics}})}else noData('c6');
if($('deep').open)renderDetails(R,E);
}
function renderDetails(R,E){
const dimKeys=['clarity','evidence','impact','action','urgency'];let bands=['1–<2','2–<3','3–<4','4–<4.5','4.5–5'];
plot('d1',bands.map((b,i)=>({type:'bar',orientation:'h',name:b,y:dimKeys.map(d=>DIM_NAMES[d]),x:dimKeys.map(d=>count(E,r=>band(r.scores[d])===b)),marker:{color:['#d8e3f1','#a7c1dd','#729cc9','#4277b1','#1e528c'][i]},hovertemplate:'%{y}: %{x} sessions · '+b+'<extra></extra>'})),{barmode:'stack',showlegend:true,legend:{orientation:'h',y:-.3},margin:{l:140,r:10,t:5,b:79},height:250});
plot('d2',['Scored','NE','IE','Unavailable'].map((s,i)=>({type:'bar',orientation:'h',name:s,y:dimKeys.map(d=>DIM_NAMES[d]),x:dimKeys.map(d=>count(E,r=>status(r,d)===s)),marker:{color:['#168a75','#a7b4c7','#a56ba4','#e1e5ed'][i]},hovertemplate:'%{y}: %{x} sessions · '+s+'<extra></extra>'})),{barmode:'stack',showlegend:true,legend:{orientation:'h',y:-.3},margin:{l:140,r:10,t:5,b:79},height:250});
let rcounts=routeOrder.filter(r=>E.some(x=>x.route===r));plot('d3',[{type:'bar',x:rcounts,y:rcounts.map(route=>count(E,r=>r.route===route)),marker:{color:rcounts.map(x=>ROUTECOL[x])},text:rcounts.map(route=>count(E,r=>r.route===route)),textposition:'outside',hovertemplate:'%{x}: %{y} sessions<extra></extra>'}],{height:230,margin:{l:45,r:15,t:26,b:55}});
let limit=Number($('detailLimit').value)||75;let rows=E.slice().sort((a,b)=>b.date.localeCompare(a.date)).slice(0,limit);$('rows').innerHTML='<table><thead><tr><th>Session</th><th>Date</th><th>Topic</th><th>Sentiment</th><th>Urgency route</th><th>Clarity</th><th>Evidence</th><th>Severity</th><th>Actionability</th><th>Human review</th><th>Principal issue</th></tr></thead><tbody>'+rows.map(r=>'<tr data-key="'+esc(r.source+'::'+r.id)+'"><td>'+esc(r.source+' / '+r.id)+'</td><td>'+esc(r.date)+'</td><td>'+esc(r.topic)+'</td><td>'+esc(r.sent)+'</td><td><span class="pill '+esc(r.route)+'">'+esc(r.route)+'</span></td>'+['clarity','evidence','impact','action'].map(d=>'<td>'+esc(safe(r.scores[d])?r.scores[d]+' / 5':status(r,d))+'</td>').join('')+'<td>'+(r.humanReview?'Flagged':'—')+'</td><td>'+esc(r.principal||r.userText.slice(0,110)||'Not available')+'</td></tr>').join('')+'</tbody></table><p class="note">Showing '+rows.length+' of '+E.length+' responding sessions under current filters; export CSV for full list.</p>';
$('rows').querySelectorAll('[data-key]').forEach(el=>el.onclick=()=>openRecord(el.dataset.key));
}
function openRecord(key){let r=DATA.find(x=>x.source+'::'+x.id===key);if(!r)return;let facts=[['Kiosk / session',r.source+' / '+r.id],['Date',r.date],['Ministry topic',topicLabel(r.topic)],['Topic classification',r.topicOrigin],['Urgency route',r.route],['Human-review flag',r.humanReview?'Yes':'No'],['Sentiment',r.sent],['Intent',r.intent],['Citizen messages',r.msgs]];
$('modalTitle').textContent='Session Assessment · '+r.id;
let cards=Object.keys(DIM_NAMES).map(d=>{let v=r.scores[d],c=r.coverage[d];return '<div class="scorebox"><small>'+esc(DIM_NAMES[d])+'</small><b>'+esc(safe(v)?v+' / 5':status(r,d))+'</b><small>'+esc(r.statuses[d])+' · Coverage '+(safe(c)?(100*c).toFixed(0)+'%':'unavailable')+'</small></div>'}).join('');
let full={};try{full=JSON.parse(r.scoreFull||'{}')}catch(e){}let raw=full.raw_ai_result||{};
let details=Object.keys(DIM_NAMES).map(d=>{let name={clarity:'issue_clarity',evidence:'evidence_strength',impact:'impact_severity',action:'request_actionability',urgency:'urgency'}[d],info=raw[name]||{};let entries=Object.entries(info).filter(([k,v])=>v&&typeof v==='object'&&!Array.isArray(v)&&('score'in v||'rationale'in v||'evidence_quotes'in v));let criterion=entries.map(([k,v])=>'<div style="border-top:1px solid #edf0f6;padding:10px 0"><b>'+esc(k.replace(/_/g,' '))+' · '+esc(v.score??'NE')+'</b><p><b>Evidence:</b> '+esc(Array.isArray(v.evidence_quotes)?v.evidence_quotes.join(' | '):'Not recorded')+'</p><p><b>Reason:</b> '+esc(v.rationale||'Not recorded')+'</p></div>').join('');return '<details><summary>'+esc(DIM_NAMES[d])+' · '+esc(safe(r.scores[d])?r.scores[d]+' / 5':status(r,d))+'</summary><p>'+esc(r.reasons[d]||'No dimension summary recorded')+'</p>'+ (criterion||'<p class="note">No criterion-level evidence stored</p>')+'</details>'}).join('');
$('modalBody').innerHTML='<div class="facts">'+facts.map(([a,b])=>'<div class="fact"><small>'+esc(a)+'</small>'+esc(b)+'</div>').join('')+'</div><h4>Five assessment dimensions</h4><div class="scoregrid">'+cards+'</div><h4>Citizen statement</h4><div class="pre">'+esc(r.userText||'Not recorded')+'</div><h4>Principal issue</h4><div class="pre">'+esc(r.principal||'Not available')+'</div><div class="criteria"><h4>Scoring rationale & criterion evidence</h4>'+details+'</div><p class="note">Model assessment; not proof of confirmed severity, resolution, or government intervention.</p>';
$('shade').classList.add('open')}
function closeModal(){$('shade').classList.remove('open')}
function csvExport(){let cols=['id','source','date','topic','topicOrigin','sent','intent','route','msgs','humanReview','principal','userText',...Object.keys(DIM_NAMES).map(x=>x+'Score')];let records=filter().map(r=>({...r,...Object.fromEntries(Object.entries(r.scores).map(([k,v])=>[k+'Score',v]))}));let csv=[cols.join(','),...records.map(r=>cols.map(c=>'"'+String(r[c]??'').replace(/"/g,'""')+'"').join(','))].join('\r\n');let a=document.createElement('a'),url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));a.href=url;a.download='citizen_issue_intelligence_filtered.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500)}
for(let id of ['source','topic','sent','route','from','to'])$(id).addEventListener('change',render);
$('reset').onclick=()=>{for(let id of ['source','topic','sent','route','from','to'])$(id).value='';render()};$('export').onclick=csvExport;
$('close').onclick=closeModal;$('shade').onclick=e=>{if(e.target===$('shade'))closeModal()};document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
$('deep').addEventListener('toggle',()=>{if($('deep').open){let R=filter();renderDetails(R,R.filter(r=>r.responded))}});
$('detailLimit').onchange=()=>{if($('deep').open){let R=filter();renderDetails(R,R.filter(r=>r.responded))}};
render();
'''
# Bind ID to a details element for rerender; keep HTML single source of truth.
BODY=BODY.replace('<details class="detail">','<details class="detail" id="deep">')

def main():
    parser=argparse.ArgumentParser(description='Generate Citizen Issue Intelligence from the scored analyzed CSV')
    parser.add_argument('--input',default='output data/analyzed.csv')
    parser.add_argument('--output',default='dengar_citizen_issue_intelligence_v9.html')
    parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args()
    source=Path(args.input)
    if not source.is_file():
        for fallback in ('analyzed(1).csv','output data/analyzed.csv','analyzed.csv'):
            if Path(fallback).is_file():source=Path(fallback);break
    if not source.is_file():raise FileNotFoundError('Analyzed CSV not found; supply --input "path/to/analyzed(1).csv"')
    df=pd.read_csv(source,low_memory=False,encoding='utf-8-sig')
    rows=prepare(df)
    if not any(any(x is not None for x in r['scores'].values()) for r in rows):
        raise ValueError('No valid scoring data. Use the fully scored analyzed(1).csv, not an older unscored analyzed.csv.')
    records=json.dumps(rows,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    js=JS.replace('__DATA__',records).replace('__TOPICS__',json.dumps(TOPICS)).replace('__DIM_NAMES__',json.dumps(DIMS))
    html='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DENGAR AI | Citizen Issue Intelligence</title><style>'+CSS+'</style><script>'+get_plotlyjs()+'</script></head><body>'+BODY+'<script>'+js+'</script></body></html>'
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(html,encoding='utf-8')
    print('Saved:',output.resolve())
    print('Sessions:',len(rows),'Citizen responses:',sum(r['responded'] for r in rows),'Scored:',sum(any(v is not None for v in r['scores'].values()) for r in rows))
    if not args.no_open:webbrowser.open(output.resolve().as_uri())

if __name__=='__main__':main()
