"""DENGAR AI - Citizen Voice & Public Concerns (standalone).
Run: python citizen_voice.py --input "output data/analyzed.csv"
Requires: pandas, plotly. Produces standalone offline HTML.
"""
from pathlib import Path
import argparse, json, webbrowser
import pandas as pd
from plotly.offline import get_plotlyjs

TOPICS={'POL':'Policing & safety','IMM':'Immigration & borders','JPN':'MyKad & civil registration','CYB':'Scams & cybercrime','FWK':'Foreign workers','GFB':'Government feedback','OTH':'Other KDN matters'}
LANG={'Malay':'#3866b7','English':'#159877','Chinese':'#c89532','Tamil':'#9265b9','Others':'#8795a8'}
def pick(df,*names,default=None):
    for name in names:
        if name in df.columns: return df[name]
    return pd.Series(default,index=df.index)
def language(v):
    v=str(v).strip().lower()
    if v in ('ms_my','malay','bahasa melayu','ms'):return 'Malay'
    if v in ('en_us','english','en','en_gb'):return 'English'
    if v in ('zh_cn','chinese','mandarin','zh','zh_tw'):return 'Chinese'
    if v in ('ta_in','tamil','ta'):return 'Tamil'
    return 'Others'
def records(df):
    if 'session_id' not in df:raise ValueError('Required column session_id not found. Please use analyzed.csv.')
    df=df.copy()
    src=pick(df,'dataset_source','dataset','source',default='Unknown').fillna('Unknown').astype(str)
    df['_source']=src.map(lambda x:'SP1' if 'sp1' in x.lower() else 'SP9' if 'sp9' in x.lower() else x)
    df=df.drop_duplicates(['_source','session_id']).reset_index(drop=True)
    dates=pd.to_datetime(pick(df,'started_at',default=None),errors='coerce',utc=True).dt.tz_convert('Asia/Kuala_Lumpur')
    counts=pd.to_numeric(pick(df,'nonempty_user_message_count','user_message_count',default=0),errors='coerce').fillna(0)
    yes=pick(df,'has_user_response',default=None)
    responded=yes.astype(str).str.lower().isin(['true','1','yes','y']) | (counts>0)
    lang=pick(df,'language_name','language_code',default='Unknown').fillna('Unknown').map(language)
    sentiments=pick(df,'session_sentiment','raw_session_sentiment',default='unavailable').fillna('unavailable').astype(str).str.lower().str.strip()
    intents=pick(df,'intent','raw_intent',default='needs_review').fillna('needs_review').astype(str).str.lower().str.strip()
    primary=pick(df,'ministry_topic_code','raw_ministry_topic_code',default='UNASSIGNED').fillna('UNASSIGNED').astype(str).str.upper()
    fallback=pick(df,'ai_validated_topic_code','raw_hm_topic_code','ai_raw_validated_topic_code',default='UNASSIGNED').fillna('UNASSIGNED').astype(str).str.upper()
    trends=pick(df,'sentiment_direction',default='').fillna('').astype(str).str.lower()
    f=pick(df,'first_user_sentiment',default='').fillna('').astype(str).str.lower()
    l=pick(df,'last_user_sentiment',default='').fillna('').astype(str).str.lower()
    messages=pick(df,'session_user_text',default='').fillna('').astype(str)
    principal=pick(df,'ai_principal_issue','raw_hm_principal_issue',default='').fillna('').astype(str)
    keywords=pick(df,'session_topic_keywords',default='').fillna('').astype(str)
    urgency=pick(df,'ai_urgency_route','raw_hm_urgency_route',default='').fillna('').astype(str)
    clarity=pd.to_numeric(pick(df,'ai_issue_clarity_score','raw_hm_issue_clarity_score',default=None),errors='coerce')
    output=[]
    for i in df.index:
        date=dates.iloc[i];p=primary.iloc[i];fb=fallback.iloc[i]
        topic=p if p in TOPICS else fb if fb in TOPICS else 'UNASSIGNED'
        origin='Primary classification' if p in TOPICS else 'AI scoring-derived' if fb in TOPICS else 'Unassigned'
        sent=sentiments.iloc[i] if sentiments.iloc[i] in ('positive','negative','neutral','mixed') and responded.iloc[i] else 'unavailable'
        intent=intents.iloc[i] if responded.iloc[i] else 'no_response'
        q=clarity.iloc[i]
        output.append({'id':str(df.at[i,'session_id']),'src':str(df.at[i,'_source']),'date':date.strftime('%Y-%m-%d') if pd.notna(date) else '', 'week':date.strftime('%G-W%V') if pd.notna(date) else '', 'lang':lang.iloc[i], 'response':bool(responded.iloc[i]),'msgs':int(counts.iloc[i]),'sent':sent,'intent':intent,'topic':topic,'origin':origin,'first':f.iloc[i] if f.iloc[i] in ('positive','negative','neutral','mixed') else '', 'last':l.iloc[i] if l.iloc[i] in ('positive','negative','neutral','mixed') else '', 'direction':trends.iloc[i],'text':messages.iloc[i][:3000] if responded.iloc[i] else '', 'issue':principal.iloc[i][:350], 'keywords':keywords.iloc[i][:350], 'urgency':urgency.iloc[i], 'clarity':round(float(q),2) if pd.notna(q) and 1<=q<=5 else None})
    return output
CSS=r'''
:root{--bg:#eff2f7;--text:#1d2a44;--muted:#748097;--line:#e3e8f1;--navy:#1a2c68}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:12px Inter,'Segoe UI',Arial,sans-serif}header{position:sticky;top:0;z-index:9;background:#17295f;color:white;padding:11px 25px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 2px 9px #18264a26}header strong{font-size:17px}header span{font-size:10px;color:#d7e3fc}.shell{max-width:1500px;margin:auto;padding:13px 20px 20px}.toolbar{position:sticky;top:52px;z-index:8;display:flex;gap:8px;flex-wrap:wrap;background:white;border:1px solid var(--line);border-radius:11px;padding:9px;margin-bottom:10px}.toolbar label{font-size:10px;color:var(--muted)}select,input,button{font-family:inherit}select,input{border:1px solid #dae1ed;border-radius:7px;padding:7px;background:white;color:#273b63;min-width:105px;font-size:11px}.toolbar button{border:1px solid #cfd7e6;background:white;padding:7px 11px;border-radius:7px;font-size:11px;cursor:pointer}.topline{display:flex;justify-content:space-between;align-items:center;margin-bottom:9px}.topline h1{margin:0;font-size:20px}.topline small{color:var(--muted)}.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px;margin-bottom:10px}.kpi{background:white;border:1px solid var(--line);border-radius:10px;padding:10px 13px;border-top:3px solid #2e54ab}.kpi:nth-child(2){border-top-color:#15936b}.kpi:nth-child(3){border-top-color:#c99641}.kpi:nth-child(4){border-top-color:#9165b4}.kpi:nth-child(5){border-top-color:#d75a6a}.kpi label{display:block;color:var(--muted);font-size:10px;font-weight:600}.kpi b{font-size:22px;display:block;margin:3px 0}.kpi small{color:var(--muted);font-size:10px}.charts{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:10px}.panel{background:white;border:1px solid var(--line);border-radius:11px;padding:11px;min-width:0;overflow:hidden}.panel h3{font-size:12px;margin:0 0 3px}.panel p{font-size:10px;color:var(--muted);margin:0 0 4px}.span7{grid-column:span 7}.span5{grid-column:span 5}.span4{grid-column:span 4}.span6{grid-column:span 6}.chart{height:245px;min-width:0}.panel select{padding:4px;min-width:135px}.flexhead{display:flex;align-items:center;justify-content:space-between;gap:6px}.detail{background:white;border:1px solid var(--line);border-radius:11px;margin-top:10px;padding:12px}.detail summary{cursor:pointer;font-weight:700;font-size:13px;color:#203668}.detail .charts{margin-top:11px}.tablewrap{max-height:360px;overflow:auto;margin-top:11px}table{width:100%;border-collapse:collapse;font-size:11px}td,th{padding:9px;border-bottom:1px solid #ebeff5;text-align:left;vertical-align:top}th{background:#f7f9fd;position:sticky;top:0}.micro,.footer{font-size:10px;color:var(--muted)}.footer{margin:12px 3px} .tags{display:flex;flex-wrap:wrap;gap:7px}.tag{border-radius:20px;background:#f0f4fb;padding:6px 9px;color:#3a5279;font-size:11px} @media(max-width:980px){.span7,.span5,.span4,.span6{grid-column:span 12}.kpis{grid-template-columns:repeat(2,1fr)}.toolbar{position:static}}@media print{header,.toolbar,.detail{display:none}.shell{padding:0}.chart{height:200px}.panel{break-inside:avoid}body{background:white}}
'''
CSS += '\n/* V7: 16:9 presentation canvas with proportional, responsive investigation area. */\nhtml{scroll-behavior:smooth}body{min-width:0}.shell{width:min(100%,1600px);max-width:1600px;margin:0 auto;padding:clamp(10px,1.1vw,19px)}.charts{grid-template-columns:repeat(12,minmax(0,1fr))}.chart{height:clamp(210px,22vh,310px)}.kpis{gap:clamp(7px,.7vw,12px)}.panel{min-width:0}.detail[open]{min-height:min(90vh,900px);scroll-margin-top:105px}.detail[open] .chart{height:clamp(245px,27vh,370px)}.detail[open] .tablewrap{max-height:clamp(350px,51vh,620px)}.tablewrap{overflow:auto} @media(min-aspect-ratio:16/9) and (min-width:1100px){.shell{width:min(98vw,calc(94vh * 16 / 9),1600px)}.chart{height:clamp(195px,21vh,300px)}} @media(max-width:950px){.shell{width:100%}}\n'

CSS += "\n/* Power BI-style 16:9 presentation mode: six overview visuals, two rows. */\n@media (min-width: 1100px) {\n  .shell { width: min(99vw, 1900px) !important; max-width: 1900px !important; padding: 7px 13px 12px !important; }\n  header { padding: 6px 18px !important; min-height: 34px; }\n  .toolbar { top: 36px !important; padding: 5px 9px !important; margin-bottom: 6px !important; gap: 5px !important; }\n  .toolbar select,.toolbar input { padding: 4px 6px !important; }\n  .toolbar button { padding: 5px 8px !important; }\n  .topline { margin-bottom: 5px !important; }\n  .topline h1 { font-size: 16px !important; }\n  .kpis { margin-bottom: 6px !important; gap: 7px !important; }\n  .kpi { padding: 5px 10px !important; min-height: 58px; }\n  .kpi label { font-size: 9px !important; }\n  .kpi b { font-size: 18px !important; margin: 0 !important; }\n  .kpi small { font-size: 9px !important; }\n  .charts { grid-template-columns: repeat(12,minmax(0,1fr)) !important; gap: 7px !important; }\n  .charts > .panel.span7,.charts > .panel.span5,.charts > .panel.span6,.charts > .panel.span4 { grid-column: span 4 !important; }\n  .charts > .panel.span12 { grid-column: span 12 !important; }\n  .panel { padding: 8px 9px !important; border-radius: 8px !important; }\n  .panel h3 { font-size: 11px !important; line-height: 1.25; }\n  .panel p { font-size: 9px !important; line-height: 1.25; margin-bottom: 3px !important; }\n  .chart { height: clamp(158px, 26vh, 250px) !important; }\n  .footer { font-size: 9px !important; margin: 5px 0 !important; }\n  .detail { margin-top: 6px !important; padding: 8px 10px !important; }\n  .detail summary { font-size: 11px !important; }\n}\n/* An investigation is its own 16:9 presentation view, not a long web page. */\n@media (min-width: 1100px) {\n  .detail[open] {\n    position: fixed !important;\n    z-index: 1000 !important;\n    top: 50% !important;\n    left: 50% !important;\n    transform: translate(-50%,-50%) !important;\n    width: min(96vw, calc(92dvh * 16 / 9), 1900px) !important;\n    height: min(92dvh, calc(96vw * 9 / 16)) !important;\n    min-height: 0 !important;\n    max-height: none !important;\n    background: #fff !important;\n    border: 2px solid #8aa4d5 !important;\n    box-shadow: 0 0 0 100vmax rgba(12,27,56,.63), 0 20px 60px #15224360 !important;\n    padding: 13px 17px !important;\n    overflow: auto !important;\n    overscroll-behavior: contain;\n  }\n  .detail[open] > summary { position: sticky; top: -13px; z-index: 10; background: #fff; padding: 10px 5px !important; border-bottom: 1px solid #e3eaf3; cursor: pointer; }\n  .detail[open] > summary::after { content: '    ✕ Close'; float: right; color: #2d52a1; font-weight: 700; }\n  .detail[open] .charts > .panel.span6, .detail[open] .charts > .panel.span7, .detail[open] .charts > .panel.span5 { grid-column: span 6 !important; }\n  .detail[open] .chart { height: clamp(200px, 29vh, 330px) !important; }\n  .detail[open] .tablewrap { max-height: clamp(230px, 37vh, 490px) !important; }\n}\n@media (max-width: 1099px) and (min-width: 700px) { .charts > .panel.span7,.charts > .panel.span5,.charts > .panel.span6 { grid-column:span 6 !important; } }\n"

HTML=r'''
<header><div><strong>DENGAR<span style="color:#f4c534">·</span>AI</strong>　 Citizen Voice & Public Concerns<br><span>Ministry of Home Affairs · Citizen concerns, intent and sentiment</span></div><span>Model classifications · Not independently verified</span></header>
<main class="shell"><div class="toolbar"><label>Source <select id="source"><option value="">All kiosks</option></select></label><label>Language <select id="lang"><option value="">All languages</option></select></label><label>Ministry topic <select id="topic"><option value="">All topics</option></select></label><label>Sentiment <select id="sent"><option value="">All sentiments</option></select></label><label>From <input id="from" type="date"></label><label>To <input id="to" type="date"></label><button id="reset">Reset filters</button></div>
<div class="topline"><h1>Citizen Voice & Public Concerns</h1><small id="scope"></small></div><div class="kpis" id="kpis"></div>
<div class="charts">
<section class="panel span7"><h3>Which Ministry concerns generate the strongest negative sentiment?</h3><p>Ranked negative share among sentiment-labelled sessions · Count shown for context</p><div id="chart1" class="chart"></div></section>
<section class="panel span5"><h3>What are citizens trying to communicate?</h3><p>Distribution of classified citizen intentions · Unassigned / needs_review excluded</p><div id="chart2" class="chart"></div></section>
<section class="panel span6"><div class="flexhead"><h3>Are public concerns improving or worsening?</h3><select id="trendtopic"><option value="">All topics</option></select></div><p>Weekly sentiment distribution · Compare the direction of classified citizen voices</p><div id="chart3" class="chart"></div></section>
<section class="panel span6"><h3>Which concerns generate complaints versus suggestions?</h3><p>Ministry topic × classified intent · Proportion within each assigned topic</p><div id="chart4" class="chart"></div></section>
<section class="panel span6"><h3>Which concerns appear across language communities?</h3><p>Language composition within each Ministry topic · 100% stacked horizontal bars</p><div id="chart5" class="chart"></div></section>
<section class="panel span6"><h3>Which Ministry topics are gaining attention?</h3><p>Share of citizen responses by topic · Previous reporting week vs latest reporting week</p><div id="chart6" class="chart"></div></section>
</div>
<details class="detail" id="further"><summary>Further Investigation — Keywords, classification coverage and citizen transcripts</summary><div class="charts"><section class="panel span6"><h3>Review-required intent classifications</h3><p>Keep unassigned intent separate from inferred citizen intentions</p><div id="detail1" class="chart"></div></section><section class="panel span6"><h3>Topic coverage by classification source</h3><p>Primary topic, scoring-derived fallback, or unassigned</p><div id="detail2" class="chart"></div></section></div><h3>Frequent extracted keywords</h3><p class="micro">Exploratory tags, not independently confirmed citizen concerns</p><div class="tags" id="keywords"></div><p class="micro" id="detailscope"></p><div class="tablewrap"><table><thead><tr><th>Date</th><th>Source</th><th>Language</th><th>Topic</th><th>Intent</th><th>Sentiment</th><th>Principal issue / citizen voice</th></tr></thead><tbody id="rows"></tbody></table></div></details>
<p class="footer">Each point represents recorded sessions, not unique citizens. Topic and intent assignments are automated; fallback topics are AI scoring-derived. Sentiment labels reflect model analysis, not verified satisfaction or service resolution. Language is the recorded session setting. Change in sentiment does not establish causal effect from the kiosk.</p></main>
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

const ALL=__DATA__,$=id=>document.getElementById(id),LANG={Malay:'#3866b7',English:'#159877',Chinese:'#c89532',Tamil:'#9265b9',Others:'#8795a8'},SENT={positive:'#15936b',negative:'#d75a6a',neutral:'#aab5c5',mixed:'#cba043',unavailable:'#8996a8'},TOP=__TOPICS__;
const fmt=n=>Number(n).toLocaleString('en-MY'),pct=(n,d)=>d?100*n/d:0,esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const lab=x=>String(x||'Unassigned').replaceAll('_',' ').replace(/\b\w/g,s=>s.toUpperCase());const topics=Object.keys(TOP),sents=['negative','neutral','positive','mixed'],langs=['Malay','English','Chinese','Tamil','Others'];
function p(id,traces,layout={}){let el=$(id);if(!el)return;v9Legend(el,traces,layout.showlegend===true);Plotly.react(el,traces,{height:245,paper_bgcolor:'white',plot_bgcolor:'white',font:{family:'Segoe UI, Arial',size:10,color:'#52627a'},margin:{l:50,r:12,t:13,b:45},xaxis:{automargin:true},yaxis:{automargin:true},showlegend:false,...layout,margin:{l:50,r:12,t:10,b:40,...(layout.margin||{}),b:Math.min((layout.margin?.b??40),43)},showlegend:false,height:el.clientHeight||245},{displayModeBar:false,responsive:true})}
function filter(){return ALL.filter(r=>(!$('source').value||r.src===$('source').value)&&(!$('lang').value||r.lang===$('lang').value)&&(!$('topic').value||r.topic===$('topic').value)&&(!$('sent').value||r.sent===$('sent').value)&&(!$('from').value||r.date>=$('from').value)&&(!$('to').value||r.date<=$('to').value))}
function count(arr,fn){const map={};arr.forEach(r=>{const k=fn(r);map[k]=(map[k]||0)+1});return map}function openTopic(t){$('topic').value=t;render()}
function setup(){for(let [id,field] of [['source','src'],['lang','lang'],['topic','topic'],['sent','sent']]){const sel=$(id);let values=id==='lang'?langs:id==='topic'?topics:id==='sent'?sents:[...new Set(ALL.map(r=>r.src))].sort();values.forEach(v=>{let o=document.createElement('option');o.value=v;o.textContent=id==='topic'?TOP[v]:lab(v);sel.appendChild(o)})}for(let id of ['trendtopic'])topics.forEach(v=>{let o=document.createElement('option');o.value=v;o.textContent=TOP[v];$(id).appendChild(o)});document.querySelectorAll('.toolbar select,.toolbar input').forEach(x=>x.addEventListener('change',render));$('reset').onclick=()=>{document.querySelectorAll('.toolbar select,.toolbar input').forEach(x=>x.value='');render()};for(let id of ['trendtopic'])$(id).addEventListener('change',render);$('further').addEventListener('toggle',()=>{if($('further').open)details(filter())});render()}
function kpis(R){let E=R.filter(r=>r.response),K=E.filter(r=>sents.includes(r.sent)),N=K.filter(r=>r.sent==='negative'),T=E.filter(r=>topics.includes(r.topic)),G=E.filter(r=>['complaint','suggestion','information_request','appreciation','casual_conversation'].includes(r.intent));let a=[['Citizen responses',fmt(E.length),`${pct(E.length,R.length).toFixed(1)}% of recorded sessions`],['Ministry-related topics',fmt(T.length),`${pct(T.length,E.length).toFixed(1)}% of responding sessions`],['Negative sentiment',K.length?pct(N.length,K.length).toFixed(1)+'%':'—',`${fmt(K.length)} sentiment-labelled sessions`],['Suggestions identified',fmt(E.filter(r=>r.intent==='suggestion').length),'Automatically classified'],['Intent assigned',E.length?pct(G.length,E.length).toFixed(1)+'%':'—','Excludes needs_review']];$('kpis').innerHTML=a.map(([t,v,n])=>`<div class="kpi"><label>${esc(t)}</label><b>${esc(v)}</b><small>${esc(n)}</small></div>`).join('')}
function chart1(E){const R=E.filter(r=>topics.includes(r.topic)&&sents.includes(r.sent));let a=topics.map(t=>{let x=R.filter(r=>r.topic===t),n=x.filter(r=>r.sent==='negative').length;return {t,n,total:x.length,rate:pct(n,x.length)}}).filter(x=>x.total).sort((a,b)=>a.rate-b.rate);p('chart1',[{type:'bar',orientation:'h',x:a.map(x=>x.rate),y:a.map(x=>TOP[x.t]),customdata:a.map(x=>[x.n,x.total]),marker:{color:a.map(x=>x.rate>=25?'#bc354b':x.rate>=10?'#e16978':'#e7a9b3')},text:a.map(x=>x.rate.toFixed(1)+'%'),textposition:'outside',cliponaxis:false,hovertemplate:'%{y}<br>Negative: %{customdata[0]} of %{customdata[1]} labelled<br>%{x:.1f}% negative<extra></extra>'}],{margin:{l:156,r:47,t:12,b:45},xaxis:{title:'Negative share (%)',range:[0,Math.max(25,...a.map(x=>x.rate))*1.23]},yaxis:{automargin:true}})}

function chart2(E){let ints=['complaint','suggestion','information_request','appreciation','casual_conversation'];let counts=ints.map(i=>E.filter(r=>r.intent===i).length);p('chart2',[{type:'pie',hole:.56,labels:ints.map(lab),values:counts,sort:false,marker:{colors:['#d75a6a','#c89532','#3866b7','#15936b','#9265b9']},textinfo:'none',hovertemplate:'%{label}<br>%{value} sessions · %{percent}<extra></extra>'}],{showlegend:true,legend:{orientation:'h',y:-.2,font:{size:9}},margin:{l:10,r:10,t:8,b:58},annotations:[{text:String(counts.reduce((a,b)=>a+b,0))+'<br><span style="font-size:10px">classified</span>',x:.5,y:.5,showarrow:false,font:{size:18,color:'#24385a'}}]})}

function chart3(E){let t=$('trendtopic').value,R=E.filter(r=>(!t||r.topic===t)&&sents.includes(r.sent)),weeks=[...new Set(R.map(r=>r.week).filter(Boolean))].sort();p('chart3',sents.map(s=>({type:'scatter',mode:'lines+markers',name:lab(s),x:weeks,y:weeks.map(w=>{let a=R.filter(r=>r.week===w);return pct(a.filter(r=>r.sent===s).length,a.length)}),line:{color:SENT[s],width:2.1},marker:{size:5},hovertemplate:'%{x} · %{y:.1f}%<extra>'+lab(s)+'</extra>'})),{showlegend:true,legend:{orientation:'h',y:-.29},margin:{l:43,r:10,t:12,b:57},yaxis:{title:'Share (%)',range:[0,100]}})}
function chart4(E){let R=E.filter(r=>topics.includes(r.topic)),ints=['complaint','suggestion','information_request','appreciation','casual_conversation','needs_review'],cs=['#d75a6a','#c89532','#3866b7','#15936b','#9265b9','#aab5c5'];p('chart4',ints.map((i,k)=>({type:'bar',orientation:'h',name:lab(i),y:topics.map(t=>TOP[t]),x:topics.map(t=>{let a=R.filter(r=>r.topic===t);return pct(a.filter(r=>r.intent===i).length,a.length)}),marker:{color:cs[k]},hovertemplate:'%{y}<br>'+lab(i)+': %{x:.1f}%<extra></extra>'})),{barmode:'stack',showlegend:true,legend:{orientation:'h',y:-.4,font:{size:9}},margin:{l:148,r:9,t:10,b:75},xaxis:{title:'Share of sessions (%)',range:[0,100]}})}
function chart5(E){const R=E.filter(r=>topics.includes(r.topic));p('chart5',langs.map(l=>({type:'bar',orientation:'h',name:l,y:topics.map(t=>TOP[t]),x:topics.map(t=>{let a=R.filter(r=>r.topic===t);return pct(a.filter(r=>r.lang===l).length,a.length)}),customdata:topics.map(t=>R.filter(r=>r.topic===t&&r.lang===l).length),marker:{color:LANG[l]},hovertemplate:'%{y}<br>'+l+': %{customdata} sessions (%{x:.1f}%)<extra></extra>'})),{barmode:'stack',showlegend:true,legend:{orientation:'h',y:-.32,font:{size:9}},margin:{l:150,r:10,t:12,b:63},xaxis:{title:'Language share (%)',range:[0,100]}})}

function chart6(E){let weeks=[...new Set(E.map(r=>r.week).filter(Boolean))].sort(),last=weeks.slice(-2),prev=E.filter(r=>r.week===last[0]),curr=E.filter(r=>r.week===last[1]);if(last.length<2){$('chart6').innerHTML='<p class="micro">At least two reporting weeks are needed for a period comparison.</p>';return}let rows=topics.map(t=>({t,a:pct(prev.filter(r=>r.topic===t).length,prev.length),b:pct(curr.filter(r=>r.topic===t).length,curr.length)})).sort((a,b)=>a.b-b.b);p('chart6',[{type:'scatter',mode:'markers',x:rows.map(x=>x.a),y:rows.map(x=>TOP[x.t]),name:last[0],line:{color:'#8da7cd',width:2},marker:{size:8,color:'#8da7cd'},hovertemplate:last[0]+' · %{y}: %{x:.1f}%<extra></extra>'},{type:'scatter',mode:'markers',x:rows.map(x=>x.b),y:rows.map(x=>TOP[x.t]),name:last[1],line:{color:'#2464ad',width:2},marker:{size:9,color:'#2464ad'},hovertemplate:last[1]+' · %{y}: %{x:.1f}%<extra></extra>'},...rows.map(x=>({type:'scatter',mode:'lines',x:[x.a,x.b],y:[TOP[x.t],TOP[x.t]],line:{color:x.b>=x.a?'#159877':'#d75a6a',width:2},showlegend:false,hoverinfo:'skip'}))],{showlegend:true,legend:{orientation:'h',y:-.3},margin:{l:150,r:10,t:12,b:61},xaxis:{title:'Share of responding sessions (%)'},yaxis:{automargin:true}})}

function details(R){let E=R.filter(r=>r.response),ints=['complaint','suggestion','information_request','appreciation','casual_conversation','needs_review','unassigned'];p('detail1',[{type:'bar',orientation:'h',y:ints.map(lab).reverse(),x:ints.map(x=>E.filter(r=>r.intent===x).length).reverse(),marker:{color:ints.map(x=>x==='needs_review'?'#cba043':'#3866b7').reverse()}}],{margin:{l:143,r:8,t:12,b:48},xaxis:{title:'Responding sessions'}});let types=['Primary classification','AI scoring-derived','Unassigned'];p('detail2',[{type:'pie',hole:.6,labels:types,values:types.map(x=>E.filter(r=>r.origin===x).length),marker:{colors:['#3866b7','#159877','#aab5c5']},textinfo:'percent',hovertemplate:'%{label}: %{value}<extra></extra>'}],{showlegend:true,legend:{orientation:'h',y:-.2},margin:{l:5,r:5,t:4,b:40}});let words={};E.forEach(r=>{let seen=new Set(r.keywords.split(/[,;|]+/).map(x=>x.trim()).filter(x=>x&&x.toLowerCase()!=='unavailable'));seen.forEach(w=>words[w]=(words[w]||0)+1)});$('keywords').innerHTML=Object.entries(words).sort((a,b)=>b[1]-a[1]).slice(0,20).map(([k,n])=>`<span class="tag">${esc(k)} · ${n}</span>`).join('')||'No extracted keywords';$('detailscope').textContent='Showing 100 most recent citizen-response sessions under current filters.';$('rows').innerHTML=E.slice().sort((a,b)=>b.date.localeCompare(a.date)).slice(0,100).map(r=>`<tr><td>${esc(r.date)}</td><td>${esc(r.src)}</td><td>${esc(r.lang)}</td><td>${esc(TOP[r.topic]||'Unassigned')}</td><td>${esc(lab(r.intent))}</td><td style="color:${SENT[r.sent]||'#8996a8'}">${esc(lab(r.sent))}</td><td>${esc((r.issue||r.text).slice(0,260))}</td></tr>`).join('')}
function render(){let R=filter(),E=R.filter(r=>r.response);$('scope').textContent=fmt(R.length)+' recorded sessions · '+fmt(E.length)+' with citizen input';kpis(R);chart1(E);chart2(E);chart3(E);chart4(E);chart5(E);chart6(E);if($('further').open)details(R)}setup();
'''
def main():
    parser=argparse.ArgumentParser(description='DENGAR Citizen Voice standalone dashboard')
    parser.add_argument('--input',default='output data/analyzed.csv');parser.add_argument('--output',default='dengar_citizen_voice_v9.html');parser.add_argument('--no-open',action='store_true');args=parser.parse_args()
    source=Path(args.input)
    if not source.exists() and args.input=='output data/analyzed.csv':source=next((p for p in [Path('analyzed(1).csv'),Path('analyzed.csv')] if p.exists()),source)
    if not source.exists():raise FileNotFoundError(f'Cannot find analyzed CSV: {source.resolve()}')
    rows=records(pd.read_csv(source,encoding='utf-8-sig',low_memory=False))
    data=json.dumps(rows,ensure_ascii=False,separators=(',',':')).replace('<','\u003c').replace('>','\u003e').replace('&','\u0026')
    js=JS.replace('__DATA__',data).replace('__TOPICS__',json.dumps(TOPICS))
    html='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>DENGAR AI | Citizen Voice</title><style>'+CSS+'</style><script>'+get_plotlyjs()+'</script></head><body>'+HTML+'<script>'+js+'</script></body></html>'
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(html,encoding='utf-8')
    print(f'Generated: {out.resolve()} | Sessions: {len(rows):,} | With citizen input: {sum(r["response"] for r in rows):,}')
    if not args.no_open:webbrowser.open(out.resolve().as_uri())
if __name__=='__main__':main()
