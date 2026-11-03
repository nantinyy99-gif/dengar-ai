"""DENGAR V5 standalone conversation dashboard. Only this Python file and the analyzed CSV are required.
Run: python conversation_scoring_view.py --input "analyzed.csv"
Jupyter: %run conversation_scoring_view.py --input "analyzed.csv" --no-open
Requires pandas. Plots use Plotly CDN when opened in a browser.
"""
from pathlib import Path
import argparse
import json
import webbrowser
import pandas as pd

EX_HTML = '\n<section class="page active" id="page-executive" aria-label="Executive overview">\n <div class="section-head"><div><div class="eyebrow">01 / Leadership overview</div><h2>Executive overview</h2><p>Concise view of recorded engagement and citizen conversation themes.</p></div></div>\n <div class="kpi-grid" id="ex-kpis"></div>\n <div class="two-col">\n  <article class="panel"><h3>Citizen intent</h3><p class="helper">Responding sessions, including unclassified intent</p><div id="ex-intent" class="plot"></div></article>\n  <article class="panel"><h3>Sentiment over time</h3><p class="helper">Share of classified sentiment by week; not a satisfaction measure</p><div id="ex-trend" class="plot"></div></article>\n  <article class="panel"><h3>Ministry topics</h3><p class="helper">Assigned topics, not verified national priorities</p><div id="ex-topics" class="list"></div></article>\n  <article class="panel"><h3>Recorded session languages</h3><p class="helper">Based on session settings, not verified spoken language</p><div id="ex-languages" class="list"></div></article>\n  <article class="panel"><h3>Recent citizen voices</h3><p class="helper">Select a transcript to see the complete session record</p><div id="ex-voices" class="list scroll-list"></div></article>\n  <article class="panel"><h3>Sessions for review</h3><p class="helper">Automatic flags are not confirmed service incidents</p><div id="ex-review" class="list scroll-list"></div></article>\n </div>\n</section>'
EX_JS = "\nfunction renderExecutive(R) {\n const E=R.filter(r=>r.responded), known=E.filter(r=>['positive','negative','neutral','mixed'].includes(r.sent));\n kpis('ex-kpis',[\n  ['Recorded sessions',R.length,'Distinct source and session ID'],\n  ['Citizen responses',E.length,`${pct(E.length,R.length).toFixed(1)}% of recorded sessions`],\n  ['Positive sentiment',known.length?pct(known.filter(r=>r.sent==='positive').length,known.length).toFixed(1)+'%':'—',`${known.length} labelled responding sessions`],\n  ['Negative sentiment',known.length?pct(known.filter(r=>r.sent==='negative').length,known.length).toFixed(1)+'%':'—','Not verified dissatisfaction']]);\n const intents=topCounts(E,'intent',8); bar('ex-intent',intents,'#3154b2',true);\n const weeks=[...new Set(known.map(r=>r.week).filter(Boolean))].sort();\n const traces=['positive','neutral','negative'].map((s,i)=>({type:'scatter',mode:'lines+markers',name:pretty(s),x:weeks,y:weeks.map(w=>{let a=known.filter(r=>r.week===w);return pct(a.filter(r=>r.sent===s).length,a.length)}),line:{color:['#15936b','#9aa9bd','#d75a6a'][i],width:2.5}}));\n plot('ex-trend',traces,{yaxis:{title:'Share (%)',range:[0,100]},legend:{orientation:'h',y:-.26},margin:{l:46,r:16,t:18,b:68}});\n miniList('ex-topics',topCounts(E.filter(r=>validTopic(r.topic)),'topic',8),k=>TOPICS[k]?`${k} · ${TOPICS[k]}`:k,'topic');\n miniList('ex-languages',topCounts(E,'lang',8),k=>k,'lang');\n sessionList('ex-voices',E.filter(r=>r.text.trim()).sort((a,b)=>b.datetime.localeCompare(a.datetime)).slice(0,7),r=>r.text.slice(0,165),r=>`${r.date} · ${r.source} · ${r.lang}`);\n sessionList('ex-review',E.filter(r=>r.review||r.scoringReview||r.coverageAudit).sort((a,b)=>b.datetime.localeCompare(a.datetime)).slice(0,7),r=>r.principalIssue&&r.principalIssue!=='Unavailable'?r.principalIssue:r.text.slice(0,135),r=>`${r.source} · ${r.date} · review flag`);\n}\n"
OP_HTML = '\n<section class="page" id="page-operations" aria-label="Operations">\n <div class="section-head"><div><div class="eyebrow">02 / Kiosk operations</div><h2>Operational analytics</h2><p>Traffic, engagement, timing and source comparisons.</p></div></div>\n <div class="kpi-grid" id="op-kpis"></div>\n <div class="two-col">\n  <article class="panel"><h3>Weekly sessions and response rate</h3><p class="helper">Bars count sessions; line shows the percentage with citizen input</p><div id="op-week" class="plot"></div></article>\n  <article class="panel"><h3>Response rate by weekday and hour</h3><p class="helper">Blank cells indicate no recorded sessions in that time slot</p><div id="op-heat" class="plot"></div></article>\n  <article class="panel"><h3>SP1 and SP9 participation</h3><p class="helper">Compare rates; higher volume does not imply higher participation</p><div id="op-source" class="plot"></div></article>\n  <article class="panel"><h3>Hourly activity</h3><p class="helper">Local Malaysia time · total recorded sessions</p><div id="op-hour" class="plot"></div></article>\n  <article class="panel"><h3>Session duration</h3><p class="helper">Recorded duration versus observed message timestamp span</p><div id="op-duration" class="plot"></div></article>\n  <article class="panel"><h3>Data quality indicators</h3><p class="helper">Diagnostics require review before conclusions about kiosk performance</p><div id="op-quality" class="list"></div></article>\n </div>\n</section>'
OP_JS = "\nfunction renderOperations(R){\n const E=R.filter(r=>r.responded),dur=R.map(r=>r.duration).filter(validNum), obs=R.map(r=>r.observed).filter(validNum);\n kpis('op-kpis',[\n ['Total sessions',R.length,'Source + session ID'],['Response rate',pct(E.length,R.length).toFixed(1)+'%',`${E.length} with citizen messages`],\n ['Median recorded duration',dur.length?(median(dur)/60).toFixed(2)+' min':'—','From session start/end timestamps'],\n ['Median observed span',obs.length?(median(obs)/60).toFixed(2)+' min':'—','First-to-last message timestamps']]);\n const weeks=[...new Set(R.map(r=>r.week).filter(Boolean))].sort();\n const totals=weeks.map(w=>R.filter(r=>r.week===w).length);\n plot('op-week',[{type:'bar',x:weeks,y:totals,name:'Sessions',marker:{color:'#3457b8'}},{type:'scatter',x:weeks,y:weeks.map(w=>{let a=R.filter(r=>r.week===w);return pct(a.filter(r=>r.responded).length,a.length)}),name:'Response rate',yaxis:'y2',mode:'lines+markers',line:{color:'#15936b',width:2.5}}],{yaxis:{title:'Sessions'},yaxis2:{title:'Response %',overlaying:'y',side:'right',range:[0,100],ticksuffix:'%'},legend:{orientation:'h',y:-.28}});\n const days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],hrs=Array.from({length:24},(_,i)=>i);\n const z=days.map(d=>hrs.map(h=>{let a=R.filter(r=>r.weekday===d&&r.hour===h);return a.length?pct(a.filter(r=>r.responded).length,a.length):null}));\n plot('op-heat',[{type:'heatmap',x:hrs,y:days,z,colorscale:[[0,'#eef3fc'],[1,'#247cbe']],zmin:0,zmax:100,colorbar:{title:'%'},hovertemplate:'%{y} · %{x}:00<br>Response rate %{z:.1f}%<extra></extra>'}],{margin:{l:92,r:46,t:12,b:46},xaxis:{dtick:3},yaxis:{autorange:'reversed'}});\n const sources=topCounts(R,'source',12).map(([s,n])=>{let e=R.filter(r=>r.source===s);return[s,n,pct(e.filter(r=>r.responded).length,e.length)]});\n plot('op-source',[{type:'bar',x:sources.map(x=>x[0]),y:sources.map(x=>x[2]),marker:{color:'#3457b8'},text:sources.map(x=>`${x[2].toFixed(1)}% (n=${x[1]})`),textposition:'outside',cliponaxis:false,hovertemplate:'%{x}<br>Response rate: %{y:.1f}%<extra></extra>'}],{yaxis:{title:'Response rate (%)',rangemode:'tozero'},margin:{l:55,r:20,t:40,b:45}});\n plot('op-hour',[{type:'bar',x:hrs,y:hrs.map(h=>R.filter(r=>r.hour===h).length),marker:{color:'#7493cd'}}],{xaxis:{dtick:2,title:'Hour (0–23)'},yaxis:{title:'Sessions'}});\n const med=[dur.length?median(dur)/60:0,obs.length?median(obs)/60:0];\n plot('op-duration',[{type:'bar',x:['Recorded','Observed messages'],y:med,marker:{color:['#3457b8','#15936b']},text:med.map(x=>x.toFixed(2)+' min'),textposition:'outside'}],{yaxis:{title:'Median minutes',rangemode:'tozero'},margin:{l:55,r:20,t:45,b:60}});\n miniList('op-quality',[\n ['Cleaning-review flags',R.filter(r=>r.cleaningReview).length],\n ['Overlapping previous sessions',R.filter(r=>r.overlap).length],\n ['Invalid or missing durations',R.filter(r=>!validNum(r.duration)).length],\n ['No citizen response',R.filter(r=>!r.responded).length],\n ['Start-time missing',R.filter(r=>!r.datetime).length]],x=>x);\n}\n"
BE_HTML = '\n<section class="page" id="page-behavior" aria-label="User behavior">\n <div class="section-head"><div><div class="eyebrow">03 / Interaction journeys</div><h2>User behavior analytics</h2><p>Consecutive session patterns and language signals. These are not unique-person estimates.</p></div><label class="control-label">Adjacent start threshold <select id="journey-gap"><option value="30">30 seconds</option><option value="60">1 minute</option><option value="120">2 minutes</option><option value="180">3 minutes</option><option value="300" selected>5 minutes</option><option value="600">10 minutes</option></select></label></div>\n <div class="kpi-grid" id="be-kpis"></div>\n <div class="two-col">\n  <article class="panel"><h3>Previous to current session</h3><p class="helper">Adjacent start times from the same kiosk source, within the threshold</p><div id="be-transition" class="plot"></div></article>\n  <article class="panel"><h3>Time between session starts</h3><p class="helper">Start-to-start interval, not waiting time for a known individual</p><div id="be-gaps" class="plot"></div></article>\n  <article class="panel"><h3>Conversation depth</h3><p class="helper">Number of recorded citizen messages per responding session</p><div id="be-depth" class="plot"></div></article>\n  <article class="panel"><h3>Language continuity</h3><p class="helper">Session settings and script hints; neither establishes speaker identity</p><div id="be-language" class="list"></div></article>\n  <article class="panel wide"><h3>Adjacent-session explorer</h3><p class="helper">Review candidate continuations with previous and next session context. Click for details.</p><div id="be-rows" class="table-wrap"></div></article>\n </div>\n</section>'
BE_JS = "\nfunction renderBehavior(R){\n const limit=Number($('journey-gap').value),A=R.filter(r=>validNum(r.gapPrev)&&r.gapPrev>=0&&r.gapPrev<=limit&&r.prevId&&r.prevId!=='Unavailable');\n const E=R.filter(r=>r.responded),back=A.filter(r=>r.responded&&r.prevEng==='no_user_response');\n const patterns=A.filter(r=>r.sequenceFlag),gaps=R.map(r=>r.gapPrev).filter(n=>validNum(n)&&n>=0);\n kpis('be-kpis',[\n ['Adjacent session pairs',A.length,`Starts within ${limit} sec`],\n ['After empty session',back.length,'Current session has citizen input'],\n ['0 → 1 → Multiple',patterns.length,'Three adjacent sessions; 5-minute sequence flag'],\n ['Median start gap',gaps.length?median(gaps).toFixed(1)+' sec':'—','All chronological gaps in filtered source']]);\n const names={no_user_response:'No response',one_user_message:'One message',multiple_user_messages:'Multiple messages'};\n const map={};A.forEach(r=>{let k=(names[r.prevEng]||r.prevEng)+' → '+(names[r.engagement]||r.engagement);map[k]=(map[k]||0)+1});\n bar('be-transition',Object.entries(map).sort((a,b)=>b[1]-a[1]).slice(0,9),'#3457b8',true);\n const bins=[[0,30],[30,60],[60,120],[120,180],[180,300],[300,600],[600,Infinity]];\n const labels=['0–30s','30–60s','1–2m','2–3m','3–5m','5–10m','10m+'];\n plot('be-gaps',[{type:'bar',x:labels,y:bins.map(([a,b])=>gaps.filter(n=>n>=a&&n<b).length),marker:{color:'#7d9bd0'}}],{yaxis:{title:'Adjacent pairs'},xaxis:{title:'Start-time gap'}});\n const groups=[['1 message',n=>n===1],['2 messages',n=>n===2],['3–4 messages',n=>n>=3&&n<=4],['5+ messages',n=>n>=5]];\n plot('be-depth',[{type:'bar',x:groups.map(x=>x[0]),y:groups.map(x=>E.filter(r=>x[1](r.msgs)).length),marker:{color:'#15936b'}}],{yaxis:{title:'Responding sessions'}});\n miniList('be-language',[\n ['Previous-session language changed',A.filter(r=>r.languageChanged).length],\n ['Multiple writing scripts in user text',E.filter(r=>r.scriptsMixed).length],\n ['Tamil script detected',E.filter(r=>r.tamilScript).length],\n ['Arabic script detected',E.filter(r=>r.arabicScript).length],\n ['Chinese characters detected',E.filter(r=>r.cjkScript).length]],k=>k);\n const candidates=A.filter(r=>r.responded||r.sequenceFlag).sort((a,b)=>a.gapPrev-b.gapPrev).slice(0,100);\n sessionTable('be-rows',candidates,[['Source',r=>r.source],['Start',r=>r.datetime.slice(0,19).replace('T',' ')],['Previous',r=>pretty(r.prevEng)],['Current',r=>pretty(r.engagement)],['Gap (sec)',r=>validNum(r.gapPrev)?r.gapPrev.toFixed(1):'—'],['Language',r=>r.lang]]);\n}\n"
CO_HTML = '\n<section class="page" id="page-conversation" aria-label="Conversation and scoring">\n <div class="section-head"><div><div class="eyebrow">04 / Citizen voice and rubric</div><h2>Conversation &amp; AI scoring</h2><p>Topic, sentiment and rubric outputs. AI scores have not been independently validated.</p></div></div>\n <div class="kpi-grid" id="co-kpis"></div>\n <div class="two-col">\n  <article class="panel"><h3>Citizen intent categories</h3><p class="helper">Automated intent classifications in responding sessions</p><div id="co-intent" class="plot"></div></article>\n  <article class="panel"><h3>Ministry topic distribution</h3><p class="helper">Assigned ministry categories, not verified case prevalence</p><div id="co-topic" class="plot"></div></article>\n  <article class="panel"><h3>Starting to ending sentiment</h3><p class="helper">Only comparable conversations with at least two citizen messages</p><div id="co-sentiment" class="plot"></div></article>\n  <article class="panel"><h3>Score availability by dimension</h3><p class="helper">Scored, NE, IE and unavailable are displayed separately</p><div id="co-status" class="plot"></div></article>\n  <article class="panel"><h3>AI score distributions</h3><p class="helper">Numeric rubric scores are preliminary model outputs</p><div id="co-scores" class="plot"></div></article>\n  <article class="panel"><h3>Urgency routing</h3><p class="helper">Routing labels; human review required before real-world action</p><div id="co-urgency" class="plot"></div></article>\n  <article class="panel"><h3>Scoring coverage audits</h3><p class="helper">Review numeric scores under 60% coverage and any legitimate exceptions</p><div id="co-audit" class="list"></div></article>\n  <article class="panel"><h3>Ministry topics by week</h3><p class="helper">Occurrence of assigned topics over time</p><div id="co-trend" class="plot"></div></article>\n  <article class="panel wide"><h3>Scored session explorer</h3><p class="helper">Open each record for the principal issue, dimension status, scores and coverage</p><div id="co-rows" class="table-wrap"></div></article>\n </div>\n</section>'
CO_JS = "\nfunction renderConversation(R){\n const E=R.filter(r=>r.responded),S=E.filter(r=>r.scored),audit=S.filter(r=>r.coverageAudit);\n const dims=['issue_clarity','evidence_strength','impact_severity','request_actionability','urgency'];\n kpis('co-kpis',[\n ['Responding sessions',E.length,'Recorded citizen messages'],\n ['Scored sessions',S.length,`${pct(S.length,E.length).toFixed(1)}% of responding sessions`],\n ['Human-review flags',S.filter(r=>r.scoringReview).length,'From AI scoring outputs'],\n ['Coverage audits',audit.length,'At least one dimension flagged']]);\n bar('co-intent',topCounts(E,'intent',9),'#3457b8',true);\n bar('co-topic',topCounts(E.filter(r=>validTopic(r.topic)),'topic',8),'#7a90c9',true);\n const pairs=topCounts(E.filter(r=>r.msgs>=2&&['positive','negative','neutral'].includes(r.firstSent)&&['positive','negative','neutral'].includes(r.lastSent)),r=>`${pretty(r.firstSent)} → ${pretty(r.lastSent)}`,9);\n bar('co-sentiment',pairs,'#15936b',true);\n const statuses=['SCORED','NE','IE','Unavailable'];const statusColors=['#3457b8','#b8c2d3','#e0b963','#e9edf3'];\n plot('co-status',statuses.map((status,i)=>({type:'bar',orientation:'h',name:status,y:dims.map(pretty),x:dims.map(d=>S.filter(r=>(r.dimensions[d]?.status||'Unavailable').toUpperCase()===status.toUpperCase()).length),marker:{color:statusColors[i]}})),{barmode:'stack',margin:{l:160,r:12,t:12,b:55},legend:{orientation:'h',y:-.25}});\n const scores=dims.map(d=>S.map(r=>r.dimensions[d]?.score).filter(validNum));\n const scoreTraces=dims.map((d,i)=>({type:'box',name:pretty(d),y:scores[i],boxpoints:false,marker:{color:['#3457b8','#15936b','#9677bf','#d2a647','#cf6678'][i]}}));\n plot('co-scores',scoreTraces,{yaxis:{title:'Score',rangemode:'tozero'},margin:{l:48,r:12,t:20,b:98},xaxis:{tickangle:-23},showlegend:false});\n bar('co-urgency',topCounts(S,'urgencyRoute',9),'#c28c3a',true);\n miniList('co-audit',dims.map(d=>[pretty(d),S.filter(r=>r.dimensions[d]?.audit).length]).concat([['Any dimension flagged',audit.length]]),k=>k);\n const weeks=[...new Set(E.map(r=>r.week).filter(Boolean))].sort(),ts=topCounts(E.filter(r=>validTopic(r.topic)),'topic',5).map(x=>x[0]);\n plot('co-trend',ts.map((t,i)=>({type:'scatter',mode:'lines+markers',name:t,x:weeks,y:weeks.map(w=>E.filter(r=>r.week===w&&r.topic===t).length),line:{width:2,color:['#3457b8','#15936b','#bd8c48','#945da5','#dc6b73'][i]}})),{legend:{orientation:'h',y:-.27},yaxis:{title:'Sessions'}});\n sessionTable('co-rows',S.sort((a,b)=>b.datetime.localeCompare(a.datetime)).slice(0,150),[['Source',r=>r.source],['Date',r=>r.date],['Principal issue',r=>(r.principalIssue||'Unavailable').slice(0,90)],['Urgency',r=>r.urgencyRoute],['Coverage audit',r=>r.coverageAudit?'Review':'—']]);\n}\n"

TOPICS = {"POL":"Policing and community safety","IMM":"Immigration and borders","JPN":"MyKad and civil registration","CYB":"Scams and cybercrime","FWK":"Foreign workers","GFB":"Government feedback","OTH":"Other ministry matters"}
DIMS = ("issue_clarity", "evidence_strength", "impact_severity", "request_actionability", "urgency")


def build_records(frame):
    if 'session_id' not in frame.columns:
        raise ValueError('Master CSV must have session_id. Run your analysis script first.')
    f = frame.copy()
    source_field = 'dataset_source' if 'dataset_source' in f else 'dataset'
    if source_field not in f:
        f['dataset_source'] = 'Unknown'
        source_field = 'dataset_source'
    # Preserve dataset-specific session identity.
    duplicates = f.duplicated([source_field, 'session_id']).sum()
    if duplicates:
        print(f'Warning: {duplicates} duplicate source/session IDs; retaining first.')
        f = f.drop_duplicates([source_field, 'session_id'])
    def col(name, default=''):
        return f[name] if name in f else pd.Series(default,index=f.index)
    def val(row, name, default=''):
        v = row.get(name, default)
        if isinstance(v, (list, dict)):
            return v
        try:
            if pd.isna(v): return default
        except (ValueError, TypeError):
            pass
        return v
    def txt(row, name, default=''):
        v = val(row, name, default)
        return str(v).strip() if v is not None else default
    def num(row, name):
        try:
            v = float(val(row, name, float('nan')))
            return v if pd.notna(v) and abs(v) != float('inf') else None
        except (ValueError, TypeError): return None
    def yes(row, name):
        return txt(row,name).lower() in ('true','1','yes','y')
    dates = pd.to_datetime(col('started_at',None),errors='coerce',utc=True).dt.tz_convert('Asia/Kuala_Lumpur')
    records=[]
    for i, row in f.iterrows():
        d=dates.loc[i]
        source=txt(row,source_field,'Unknown')
        if source not in ('SP1','SP9'):
            source='SP1' if 'sp1' in source.lower() else 'SP9' if 'sp9' in source.lower() else 'Unknown'
        lang=txt(row,'language_name','Unknown') or 'Unknown'
        aliases={'ms_my':'Malay','ta_in':'Tamil','en_us':'English','zh_cn':'Chinese','ar_sa':'Arabic','ko_kr':'Korean'}
        lang=aliases.get(lang.lower(),lang)
        if lang.lower() in ('unknown','unavailable'):
            lang=aliases.get(txt(row,'language_code').lower(),lang)
        responded=yes(row,'has_user_response') if 'has_user_response' in f else (num(row,'nonempty_user_message_count') or 0)>0
        sent=txt(row,'session_sentiment','unavailable').lower()
        if not responded or sent not in ('positive','neutral','negative','mixed'):sent='unavailable'
        topic=txt(row,'ministry_topic_code','UNASSIGNED').upper()
        if topic not in TOPICS:topic='UNASSIGNED'
        dims={}
        for dim in DIMS:
            dims[dim]={
                'score':num(row,f'ai_{dim}_score'),
                'coverage':num(row,f'ai_{dim}_coverage'),
                'status':txt(row,f'ai_{dim}_status','Unavailable') or 'Unavailable',
                'reason':txt(row,f'ai_{dim}_reason'),
                'audit':yes(row,f'ai_{dim}_coverage_audit')}
        records.append({
            'id':txt(row,'session_id'), 'source':source,
            'datetime':d.isoformat() if pd.notna(d) else '',
            'date':d.strftime('%Y-%m-%d') if pd.notna(d) else '',
            'weekday':d.strftime('%A') if pd.notna(d) else '',
            'week':d.strftime('%G-W%V') if pd.notna(d) else '',
            'hour':int(d.hour) if pd.notna(d) else None,
            'lang':lang, 'languageCode':txt(row,'language_code'),
            'responded':bool(responded), 'sent':sent,
            'intent':txt(row,'intent','unassigned').lower() or 'unassigned',
            'topic':topic,'topicName':txt(row,'ministry_topic_name'),
            'text':txt(row,'session_user_text') if responded else '',
            'aiText':txt(row,'session_ai_text'), 'timeline':txt(row,'message_timeline_json'), 'keywords':txt(row,'session_topic_keywords'),
            'msgs':num(row,'nonempty_user_message_count') or 0, 'aiMsgs':num(row,'nonempty_ai_message_count') or 0,
            'duration':num(row,'recorded_duration_seconds'), 'endsWithUser':yes(row,'ends_with_user_message'),
            'observed':num(row,'observed_message_span_seconds'),
            'review':yes(row,'analysis_review_required'),
            'cleaningReview':yes(row,'cleaning_review_required'),
            'scored':yes(row,'ai_scoring_available'),
            'scoringReview':yes(row,'ai_human_review_required'),
            'coverageAudit':yes(row,'ai_coverage_audit_required'),
            'principalIssue':txt(row,'ai_principal_issue'),
            'scoringFull':txt(row,'ai_scoring_full_json'),
            'humanReviewReason':txt(row,'ai_human_review_reason'),
            'rubricVersion':txt(row,'ai_rubric_version'),
            'urgencyRoute':txt(row,'ai_urgency_route') or txt(row,'ai_calc_urgency_route') or txt(row,'ai_urgency_status') or 'Unavailable',
            'dimensions':dims,
            'sentimentScore':num(row,'session_sentiment_score'),
            'firstSent':txt(row,'first_user_sentiment').lower(),
            'lastSent':txt(row,'last_user_sentiment').lower(),
            'gapPrev':num(row,'previous_start_gap_seconds'),
            'gapNext':num(row,'next_start_gap_seconds'),
            'prevEng':txt(row,'previous_engagement_type','Unavailable'),
            'nextEng':txt(row,'next_engagement_type','Unavailable'),
            'engagement':txt(row,'engagement_type','Unavailable'),
            'prevId':txt(row,'previous_session_id',''),
            'nextId':txt(row,'next_session_id',''),
            'languageChanged':yes(row,'previous_language_changed'),
            'scriptsMixed':yes(row,'user_multiple_scripts'),
            'tamilScript':yes(row,'user_has_tamil_script'),
            'arabicScript':yes(row,'user_has_arabic_script'),
            'cjkScript':yes(row,'user_has_cjk_script'),
            'sequenceFlag':yes(row,'zero_one_multiple_sequence_end'),
            'overlap':yes(row,'previous_session_overlap'),
        })
    return records

# Override only the executive page presentation; other four-page modules are untouched.
EX_HTML = '''
<section class="page active" id="page-executive" aria-label="Executive overview">
 <div class="section-head"><div><div class="eyebrow">Leadership overview</div><h2>Executive overview</h2><p>Citizen engagement and reported issues at a glance</p></div><span class="section-aside">All records are drawn from the current selection</span></div>
 <div class="kpi-grid" id="ex-kpis"></div>
 <div class="panel executive-agenda"><div class="panel-top"><div><h3>Citizen agenda — recent issues</h3><p class="helper">Recent principal issues and sentiment by ministry topic</p></div><span class="section-aside">Sentiment labels and model-extracted issues; not verified priorities</span></div><div id="ex-agenda" class="agenda-grid"></div></div>
 <div class="executive-main">
  <div class="executive-left">
   <article class="panel"><h3>Citizen intent</h3><p class="helper">Classification of responding sessions, including unassigned records</p><div id="ex-intent" class="plot"></div></article>
   <article class="panel"><h3>Ministry concerns</h3><p class="helper">Select a topic for volume trends, common issues and underlying sessions</p><div id="ex-topics" class="list"></div></article>
   <article class="panel"><h3>Engagement summary</h3><p class="helper">Recorded participation by conversation depth</p><div id="ex-engagement" class="list"></div></article>
  </div>
  <div class="executive-side">
   <article class="panel"><h3>Sentiment trend</h3><p class="helper">Weekly share among sentiment-labelled conversations</p><div id="ex-trend" class="plot compact"></div></article>
   <article class="panel"><h3>Sentiment split</h3><p class="helper">Includes all labelled responding sessions</p><div id="ex-donut" class="plot donut-plot"></div></article>
   <article class="panel"><h3>Recorded session languages</h3><p class="helper">Session language setting, not verified spoken language</p><div id="ex-languages" class="list"></div></article>
  </div>
 </div>
 <div class="panel"><div class="panel-top"><div><h3>Frequent topic keywords</h3><p class="helper">Exploratory model keywords; counts reflect occurrences across responding sessions</p></div></div><div id="ex-keywords" class="keyword-flow"></div></div>
 <div class="two-col lower-grid">
  <article class="panel"><h3>Latest citizen voices</h3><p class="helper">Recent conversations with sentiment indicators. Select a row to inspect details.</p><div id="ex-voices" class="list scroll-list"></div></article>
  <article class="panel"><h3>Sessions needing review</h3><p class="helper">Automatically flagged classifications or scoring; not confirmed escalations</p><div id="ex-review" class="list scroll-list"></div></article>
 </div>
</section>'''
EX_JS = r'''
function renderExecutive(R){
 const E=R.filter(r=>r.responded), known=E.filter(r=>['positive','negative','neutral','mixed'].includes(r.sent));
 kpis('ex-kpis',[
 ['Recorded sessions',R.length,'Unique dataset and session ID'],
 ['Citizen responses',E.length,`${pct(E.length,R.length).toFixed(1)}% of all sessions`],
 ['Positive sentiment',known.length?pct(known.filter(r=>r.sent==='positive').length,known.length).toFixed(1)+'%':'—',`${known.length} labelled conversations`],
 ['Negative sentiment',known.length?pct(known.filter(r=>r.sent==='negative').length,known.length).toFixed(1)+'%':'—','Of labelled conversations']]);
 const agenda=topCounts(E.filter(r=>validTopic(r.topic)),'topic',6);
 $('ex-agenda').innerHTML=agenda.length?agenda.map(([topic,n],i)=>`<button type="button" class="agenda-card" data-topic="${esc(topic)}"><span class="agenda-name">${esc(TOPICS[topic]||topic)}</span><span class="agenda-code">${esc(topic)}</span><span class="agenda-count">${n.toLocaleString()} sessions</span></button>`).join(''):'<div class="empty">No ministry topics assigned in the current selection.</div>';
 $('ex-agenda').querySelectorAll('[data-topic]').forEach(e=>e.onclick=()=>{ $('filter-topic').value=e.dataset.topic; render()});
 const intents=topCounts(E,'intent',8);
 bar('ex-intent',intents,'#2e4fa6',true);
 if(window.Plotly&&intents.length)Plotly.relayout('ex-intent', {height:Math.max(215,Math.min(320,100+intents.length*32)), 'margin.l':175,'margin.b':35});
 const weeks=[...new Set(known.map(r=>r.week).filter(Boolean))].sort();
 plot('ex-trend',['positive','negative','neutral'].map((label,i)=>({type:'scatter',mode:'lines+markers',name:pretty(label),x:weeks,y:weeks.map(w=>{let z=known.filter(r=>r.week===w);return pct(z.filter(r=>r.sent===label).length,z.length)}),line:{color:['#15936b','#d75a6a','#a0acbd'][i],width:2.2}})),{height:230,yaxis:{title:'Share (%)',range:[0,100]},legend:{orientation:'h',y:-.30},margin:{l:45,r:12,t:9,b:60},showlegend:true});
 const sentiments=['positive','neutral','negative','mixed'],colors=['#15936b','#bac2cf','#d75a6a','#d1a545'];let totals=sentiments.map(x=>known.filter(r=>r.sent===x).length);
 plot('ex-donut',[{type:'pie',hole:.69,labels:sentiments.map(pretty),values:totals,marker:{colors},textinfo:'none',hovertemplate:'%{label}: %{value} (%{percent})<extra></extra>'}],{height:188,margin:{l:3,r:3,t:2,b:2},showlegend:true,legend:{x:1.0,y:.72,font:{size:10}},annotations:[{x:.5,y:.5,showarrow:false,text:String(known.length),font:{size:19,color:'#24334d'}}]});
 const lang=topCounts(E,'lang',7),lm=Math.max(1,...lang.map(x=>x[1]));
 $('ex-languages').innerHTML=lang.map(([name,n])=>`<div class="metric-line"><span class="metric-label">${esc(name)}</span><div class="metric-track"><span style="width:${100*n/lm}%"></span></div><span class="metric-n">${n.toLocaleString()}</span></div>`).join('')||'<div class="empty">No recorded language</div>';
 miniList('ex-topics',topCounts(E.filter(r=>validTopic(r.topic)),'topic',9),k=>TOPICS[k]?`${k} · ${TOPICS[k]}`:k);
 miniList('ex-engagement', [['No citizen response',R.length-E.length],['One citizen message',E.filter(r=>r.msgs===1).length],['Two or more citizen messages',E.filter(r=>r.msgs>=2).length],['AI scoring available',E.filter(r=>r.scored).length]]);
 let latest=E.filter(r=>r.text.trim()).sort((a,b)=>b.datetime.localeCompare(a.datetime)).slice(0,8);
 $('ex-voices').innerHTML=latest.length?latest.map(r=>`<button type="button" class="voice-card" data-key="${esc(r.source+'::'+r.id)}"><span class="sent-dot ${esc(r.sent)}"></span><span class="voice-text"><span class="voice-sentence">${esc(r.text.slice(0,200))}${r.text.length>200?'…':''}</span><span class="voice-meta">${esc(r.date)} · ${esc(r.source)} · ${esc(r.lang)} · ${esc(pretty(r.sent))}${validNum(r.sentimentScore)?' · sentiment score '+r.sentimentScore.toFixed(2):''}</span></span></button>`).join(''):'<div class="empty">No recent citizen responses</div>';
 $('ex-voices').querySelectorAll('[data-key]').forEach(e=>e.onclick=()=>openRecord(e.dataset.key));
 let flags=E.filter(r=>r.scoringReview||r.coverageAudit||r.review).sort((a,b)=>b.datetime.localeCompare(a.datetime)).slice(0,8);
 $('ex-review').innerHTML=flags.length?flags.map(r=>`<button type="button" class="review-row" data-key="${esc(r.source+'::'+r.id)}"><span class="review-main">${esc(r.principalIssue||r.text.slice(0,130)||'Session review')}</span><span class="voice-meta">${esc(r.source)} · ${esc(r.date)} · ${r.scoringReview?'Human-review flag':r.coverageAudit?'Scoring-coverage check':'Classification / analysis review'}</span></button>`).join(''):'<div class="empty">No sessions flagged in current selection</div>';
 $('ex-review').querySelectorAll('[data-key]').forEach(e=>e.onclick=()=>openRecord(e.dataset.key));
}
'''

# Keep the operations page focused on recorded session metrics; observed message span remains in CSV, not dashboard.
OP_HTML = OP_HTML.replace('<article class="panel"><h3>Session duration</h3><p class="helper">Recorded duration versus observed message timestamp span</p><div id="op-duration" class="plot"></div></article>', '')
OP_JS = OP_JS.replace("['Median observed span',obs.length?(median(obs)/60).toFixed(2)+' min':'—','First-to-last message timestamps']", "['One-message conversations',E.filter(r=>r.msgs===1).length,'Among responding sessions']")


# V4: retain page modules; enhance display content without editing them.
OP_HTML=OP_HTML.replace('Weekly sessions and response rate','Weekly participation trends').replace('Response rate by weekday and hour','Participation by weekday and hour').replace('SP1 and SP9 participation','Kiosk user participation').replace('Hourly activity','Hourly kiosk activity')
OP_HTML=OP_HTML.replace('Bars count sessions; line shows the percentage with citizen input','Session volume (bars) and participation rate (separate chart axis)')
OP_HTML=OP_HTML.replace('Response rate (%)','Participation rate (%)')
BE_HTML=BE_HTML.replace('Previous to current session','Adjacent session engagement transitions').replace('Time between session starts','Time between session starts · exclusive intervals')
CO_HTML=CO_HTML.replace('Scoring coverage audits','Scoring rule checks').replace('Review numeric scores under 60% coverage and any legitimate exceptions','Technical rubric-rule flags, separate from human-review decisions')
CO_HTML=CO_HTML.replace('  <article class="panel wide"><h3>Scored session explorer', '''  <article class="panel wide"><h3>Intent trends over time</h3><p class="helper">Weekly counts of classified intent categories; based on responding sessions</p><div id="co-intent-trend" class="plot"></div></article>
  <article class="panel"><h3>Topic and intent association</h3><p class="helper">Each bubble represents sessions assigned to a topic and intent. One primary ministry topic per session.</p><div id="co-topic-assoc" class="plot"></div></article>
  <article class="panel"><h3>Intent and sentiment association</h3><p class="helper">Bubble size represents the number of classified sessions</p><div id="co-intent-assoc" class="plot"></div></article>
  <article class="panel wide"><h3>Rubric strength levels</h3><p class="helper">Descriptive score bands (1–&lt;2 very low, 2–&lt;3 low, 3–&lt;4 moderate, 4–&lt;4.5 strong, 4.5–5 very strong). Not official rubric labels.</p><div id="co-strength" class="plot"></div></article>
  <article class="panel wide"><h3>Scored session explorer''')

CSS = r'''
:root{--blue:#2b50b7;--navy:#192b49;--ink:#24334d;--muted:#758399;--bg:#f4f6fb;--border:#e3e9f2;--green:#15936b;--red:#d75a6a}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 Inter,'Segoe UI',Arial,sans-serif;font-weight:400}
button,input,select{font:inherit}button{cursor:pointer}header{background:#fff;border-bottom:1px solid var(--border)}
.header-inner{max-width:1440px;margin:auto;padding:17px 24px;display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}
.brand{font-size:18px;color:var(--blue);font-weight:750;white-space:nowrap}.brand span{color:#d9274a}.brand-sub{color:var(--muted);font-size:11px;font-weight:400}
.nav{display:flex;align-items:center;gap:5px;flex-wrap:wrap}.nav button{background:transparent;border:1px solid transparent;border-radius:9px;padding:9px 12px;color:#5b6b83;font-weight:500;font-size:12px;white-space:nowrap}.nav button.active{color:var(--blue);background:#eef2fd;border-color:#dfe7fc;font-weight:650}.nav button:focus-visible,.toolbar :focus-visible{outline:2px solid var(--blue)}
main{max-width:1440px;margin:0 auto;padding:22px 24px 50px}.toolbar{background:#fff;border:1px solid var(--border);border-radius:14px;padding:13px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:20px}
.toolbar input,.toolbar select,.control-label select{padding:9px 11px;min-height:39px;border:1px solid #dce4f0;border-radius:9px;color:var(--ink);background:#fff;font-weight:400;min-width:0}
.toolbar input[type=search]{flex:1 1 220px}.toolbar select{flex:1 1 135px;max-width:190px}.toolbar input[type=date]{width:155px}.toolbar button,.smallbtn{border:1px solid #dce4f0;background:#fff;border-radius:9px;padding:9px 12px;color:var(--ink);font-weight:500}
.page{display:none}.page.active{display:block}.section-head{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:14px;margin:5px 0 18px}.eyebrow{color:#5375b6;font-size:11px;letter-spacing:.6px;font-weight:650}.section-head h2{font-size:22px;font-weight:650;margin:2px 0 3px;letter-spacing:-.3px}.section-head p{margin:0;color:var(--muted);font-size:12px;max-width:720px}.control-label{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--muted)}
.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin-bottom:15px}.kpi{background:#fff;border:1px solid var(--border);border-left:3px solid var(--blue);border-radius:13px;padding:17px;min-width:0}.kpi:nth-child(2){border-left-color:var(--green)}.kpi:nth-child(3){border-left-color:#bc8d4a}.kpi:nth-child(4){border-left-color:#8d75b9}.kpi-label{font-size:11px;color:#6e7b90;font-weight:550}.kpi-value{font-size:26px;line-height:1.3;font-weight:650;margin:5px 0 4px;overflow-wrap:anywhere}.kpi-note{font-size:11px;color:var(--muted);line-height:1.5;font-weight:400}
.two-col{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px;align-items:stretch}.panel{min-width:0;background:#fff;border:1px solid var(--border);border-radius:15px;padding:18px;overflow:hidden}.panel.wide{grid-column:1/-1}.panel h3{font-size:14px;font-weight:620;margin:0 0 3px;color:var(--navy)}.helper{font-size:11px;color:var(--muted);margin:0 0 13px;font-weight:400;line-height:1.6}.plot{height:315px;width:100%;min-width:0}.list{min-height:175px}.listrow{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:11px 2px;border-bottom:1px solid #eef1f7}.listrow:last-child{border-bottom:0}.listrow .name{flex:1;min-width:0;overflow-wrap:anywhere;font-size:12px;font-weight:430;line-height:1.55}.listrow .amount{flex:none;font-size:12px;color:var(--navy);font-weight:600}.scroll-list{max-height:360px;overflow-y:auto}.session-row{cursor:pointer;text-align:left;background:none;width:100%;border:0;border-bottom:1px solid #edf0f6;padding:11px 2px;color:var(--ink);font-weight:400}.session-row:hover,.data-table tbody tr:hover{background:#f6f8fe}.session-row .snippet{display:block;line-height:1.6;overflow-wrap:anywhere}.session-row .meta{font-size:10px;color:var(--muted);margin-top:5px}.empty{color:var(--muted);padding:18px 0;font-size:12px}.table-wrap{width:100%;overflow:auto;max-height:470px}.data-table{border-collapse:collapse;width:100%;font-size:11px;min-width:640px}.data-table th{text-align:left;color:#65758c;background:#f8faff;position:sticky;top:0;font-weight:600;z-index:1}.data-table th,.data-table td{padding:11px 12px;border-bottom:1px solid #e9edf4;vertical-align:top;overflow-wrap:anywhere;max-width:370px}.data-table tbody tr{cursor:pointer}
.footer{font-size:11px;color:var(--muted);line-height:1.7;margin-top:22px}.modal-shade{position:fixed;inset:0;display:none;background:#12214499;z-index:20;padding:20px;align-items:center;justify-content:center}.modal-shade.open{display:flex}.modal{width:min(880px,100%);max-height:92vh;overflow:auto;background:#fff;border-radius:18px;padding:24px}.modal-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.modal h3{margin:0;font-size:17px;font-weight:650}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:16px 0}.fact{padding:11px;border:1px solid var(--border);border-radius:9px;min-width:0;overflow-wrap:anywhere}.fact small{display:block;color:var(--muted);font-size:10px;margin-bottom:4px}.pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f9fd;border-radius:9px;padding:13px;max-height:300px;overflow:auto;font-size:12px;line-height:1.65}.detail-score{border-bottom:1px solid var(--border);padding:10px 0;font-size:12px;font-weight:400}.detail-score b{font-weight:600}body.modal-open{overflow:hidden}
@media(max-width:950px){.two-col{grid-template-columns:1fr}.panel.wide{grid-column:1}.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.header-inner{align-items:flex-start}}
@media(max-width:600px){main{padding:15px 12px 35px}.header-inner{padding:14px}.kpi-grid{gap:9px}.kpi{padding:13px}.kpi-value{font-size:22px}.toolbar select,.toolbar input[type=date]{max-width:none;flex:1 1 130px}.detail-grid{grid-template-columns:1fr}.section-head h2{font-size:19px}.nav button{padding:7px 9px;font-size:11px}}
'''

CSS += r'''
/* Executive styling aligned to the provided boss reference: orderly hierarchy, balanced right rail */
.section-aside{color:#8a96a8;font-size:11px;font-weight:400}.executive-agenda{margin:14px 0}.panel-top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:flex-start}
.agenda-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.agenda-card{border:1px solid #e7ebf3;border-left:3px solid #d5a22c;background:#fff;border-radius:10px;padding:14px;text-align:left;min-width:0;display:flex;flex-direction:column;gap:7px;font-weight:400;min-height:108px}
.agenda-card:nth-child(3n+1){border-left-color:#3b5497}.agenda-name{font-size:12px;font-weight:600;overflow-wrap:anywhere;line-height:1.4}.agenda-code{font-size:11px;color:#8792a4}.agenda-count{font-size:12px;color:#273f83;font-weight:600}
.executive-main{display:grid;grid-template-columns:minmax(0,1.26fr) minmax(340px,.84fr);gap:14px;margin:14px 0}.executive-main>.panel{min-width:0}.executive-side{display:grid;grid-template-columns:1fr;gap:14px;min-width:0}.lower-grid{margin-top:14px}.plot.compact{height:230px}.donut-plot{height:188px}
.metric-line{display:grid;grid-template-columns:130px minmax(0,1fr) 48px;align-items:center;gap:12px;padding:8px 1px;font-size:12px}.metric-track{height:7px;background:#edf1f7;border-radius:20px;overflow:hidden}.metric-track span{display:block;height:100%;background:#304c9b;border-radius:20px}.metric-n{text-align:right;color:#34415e;font-variant-numeric:tabular-nums}
.voice-card,.review-row{display:flex;text-align:left;width:100%;gap:10px;border:0;border-bottom:1px solid #edf0f5;background:transparent;padding:12px 3px;color:var(--ink);font-weight:400}.voice-card:hover,.review-row:hover{background:#f8faff}.sent-dot{margin-top:7px;flex:0 0 8px;height:8px;border-radius:50%;background:#aab3c2}.sent-dot.positive{background:#169c68}.sent-dot.negative{background:#d34b5c}.sent-dot.mixed{background:#c9a245}.voice-text{display:block;min-width:0}.voice-sentence{font-size:12px;display:block;line-height:1.6;overflow-wrap:anywhere}.voice-meta{display:block;font-size:11px;line-height:1.5;color:#8793a7;margin-top:5px}.review-row{flex-direction:column;border-left:3px solid #d9b46b;margin:4px 0 8px;padding:10px 12px;border-radius:8px;background:#fffaf1;border-bottom:0;gap:3px}.review-main{font-size:12px;line-height:1.5;font-weight:500;overflow-wrap:anywhere}
/* Modal scoring cards / nested explanations */
.modal{width:min(1000px,calc(100vw - 36px))}.modal h4{font-size:15px;font-weight:650;margin:24px 0 9px}.detail-grid{gap:9px}.fact{padding:10px 12px}.fact small{font-size:11px}.fact{font-size:13px}.detail-grid.compact-facts{grid-template-columns:repeat(3,minmax(0,1fr))}
.scoring-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.score-card{display:block;width:100%;min-height:103px;text-align:left;padding:13px 15px;border:1px solid #dce5f5;border-radius:11px;background:#f8faff;color:#253754;font-weight:400;transition:background .12s,border-color .12s}.score-card:hover,.score-card:focus-visible{background:#edf3ff;border-color:#9cb5ed;outline:none}.score-card .score-label{font-size:12px;color:#6d7e98;display:block}.score-card .score-number{font-size:18px;font-weight:650;display:block;margin:2px 0}.score-card .score-hint{color:#556b98;font-size:11px}.score-explanation{background:#fff;border:1px solid #dce5f5;border-radius:12px;padding:15px;margin-top:14px;overflow-wrap:anywhere}.criterion{border-top:1px solid #e6eaf1;padding:13px 0}.criterion:first-of-type{border-top:0}.criterion-title{font-weight:650;font-size:13px}.criterion-meta{font-size:11px;color:#64758d;margin-top:3px}.criterion-quote{border-left:3px solid #b5c5e7;padding:8px 11px;margin:7px 0;background:#f8faff;color:#374762;font-size:12px;white-space:pre-wrap}.criterion-reason{font-size:12px;line-height:1.6;margin-top:7px}.detail-tag{font-size:11px;background:#eef3fb;border-radius:7px;padding:4px 7px;color:#3a5686;display:inline-block;margin:3px 6px 3px 0}.explorer-wrap{overflow:auto;max-height:530px;max-width:100%}.explorer-table{border-collapse:collapse;min-width:900px;width:100%;font-size:12px}.explorer-table th{background:#fff;position:sticky;top:0;z-index:1;text-align:left;color:#435571;font-size:12px;font-weight:650;padding:12px 11px;border-bottom:1px solid #dce3ed;white-space:nowrap}.explorer-table td{padding:12px 11px;border-bottom:1px solid #e6ebf3;vertical-align:top;line-height:1.6;font-weight:400;overflow-wrap:anywhere}.explorer-table tr[data-key]{cursor:pointer}.explorer-table tr[data-key]:hover{background:#f5f8ff}.explorer-table .issue-cell{min-width:270px;max-width:440px}.explorer-table .short-id{max-width:135px;overflow-wrap:anywhere;color:#2f4d93}.explorer-table .status-pill{border-radius:6px;background:#edf1f8;padding:4px 8px;font-size:11px;white-space:nowrap;display:inline-block}.status-pill.negative{background:#fde8ed;color:#a92b43}.status-pill.positive{background:#ddf4e9;color:#147553}
.executive-main{align-items:start;grid-template-columns:minmax(0,1.27fr) minmax(340px,.83fr)}
.executive-left,.executive-side{display:flex;flex-direction:column;gap:14px;min-width:0}
.executive-left>.panel,.executive-side>.panel{flex:none;min-width:0}
#ex-intent{height:270px;min-height:215px}
.scoring-cards{grid-template-columns:repeat(2,minmax(0,1fr))}
.score-explanation{padding:20px;border-color:#dce5f5;background:white}
.score-explanation>.dimension-heading{font-size:16px;font-weight:650;margin:0 0 4px}
.score-explanation>.dimension-summary{font-size:12px;color:#71809a;margin:0 0 16px;line-height:1.65}
.score-explanation>.calculation-reason{font-size:12px;line-height:1.65;color:#5c6b80;padding:11px 13px;background:#f6f8fc;border-radius:9px;margin:0 0 13px}
.criterion-list{display:grid;grid-template-columns:1fr;gap:12px}
.criterion-evidence-card{padding:17px 19px;border:1px solid #dfe7f4;border-radius:12px;background:#fff;min-width:0}
.criterion-evidence-card h5{margin:0 0 10px;font-size:14px;font-weight:650;line-height:1.45;color:#263754}
.criterion-evidence-card .evidence-row{font-size:13px;line-height:1.7;margin:7px 0;overflow-wrap:anywhere}
.criterion-evidence-card .field-name{font-weight:600;color:#263754}
.criterion-evidence-card .evidence-quotes{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}
.criterion-evidence-card .confidence-row{font-size:12px;color:#718098;margin-top:9px}
.criterion-evidence-card .unavailable-row{font-size:12px;color:#8794a8;margin:8px 0}
.score-explanation .overall-notes{font-size:12px;line-height:1.7;padding:12px 15px;background:#f6f8fc;border-radius:10px;margin-top:15px}
@media(max-width:950px){.executive-main{grid-template-columns:1fr}.agenda-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.agenda-grid{grid-template-columns:1fr}.scoring-cards,.detail-grid.compact-facts{grid-template-columns:1fr}.metric-line{grid-template-columns:95px 1fr 35px}.section-aside{display:none}}
'''


CSS += r'''
.keyword-flow{display:flex;flex-wrap:wrap;gap:9px;padding:6px 0 0}.keyword-pill{display:inline-flex;gap:10px;align-items:center;border:1px solid #e3e9f3;background:#f7f9fd;color:#364967;border-radius:999px;padding:8px 11px;font-size:12px;font-weight:400}.keyword-pill small{color:#7d8ba1;font-weight:600}
.agenda-card .agenda-code{line-height:1.5}.agenda-card .sent-marker{font-size:11px;font-weight:600}.agenda-card.negative{border-left-color:#d45d67}.agenda-card.positive{border-left-color:#168c64}.agenda-card.neutral{border-left-color:#a5afc0}.agenda-name{min-height:32px}.agenda-card{justify-content:space-between;min-height:160px}.agenda-card .issue-preview{font-size:12px;line-height:1.55;color:#52617a;font-weight:400;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.topic-explore{margin-top:18px}.topic-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0}.topic-metric{border:1px solid #e4eaf4;background:#f8faff;border-radius:10px;padding:13px;font-size:12px}.topic-metric strong{display:block;font-size:20px;font-weight:650;margin-top:6px}.topic-list-button{display:block;background:#fff;border:0;border-bottom:1px solid #e9edf4;text-align:left;width:100%;padding:12px 5px;font-size:12px;line-height:1.6;color:#2c3d58;cursor:pointer}.topic-list-button:hover{background:#f7faff}.topic-list-button small{display:block;color:#8390a4;font-size:11px;margin-top:4px}.topic-spark{height:245px;width:100%}.agenda-card:hover{background:#f8faff;border-color:#c6d4e7}.panel .plot{min-width:0;overflow:visible}.two-col .panel{min-width:0}.review-row .voice-meta{font-weight:400}.negative-reason-list{display:grid;grid-template-columns:1fr 1fr;gap:12px}.negative-reason{border:1px solid #e3e9f2;border-radius:11px;padding:13px;font-size:12px;line-height:1.6;min-width:0}.negative-reason h4{margin:0 0 5px;font-size:13px;font-weight:600}.negative-reason .label{color:#71809a;font-size:11px}
@media(max-width:720px){.topic-metrics{grid-template-columns:1fr}.negative-reason-list{grid-template-columns:1fr}}
'''

JS = r'''
const ALL=__DATA__,TOPICS=__TOPICS__;const $=id=>document.getElementById(id);
const pretty=x=>String(x??'Unavailable').replace(/_/g,' ').replace(/\b\w/g,m=>m.toUpperCase());
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const validNum=x=>typeof x==='number'&&Number.isFinite(x);const pct=(a,b)=>b?100*a/b:0;
const median=a=>{if(!a.length)return null;let b=[...a].sort((x,y)=>x-y),i=Math.floor(b.length/2);return b.length%2?b[i]:(b[i-1]+b[i])/2};
const validTopic=t=>t&&t!=='UNASSIGNED'&&t!=='UNKNOWN';
function topCounts(rows,key,limit=20){let m=new Map();rows.forEach(r=>{let k=typeof key==='function'?key(r):r[key];k=String(k||'Unavailable');m.set(k,(m.get(k)||0)+1)});return [...m].sort((a,b)=>b[1]-a[1]).slice(0,limit)}
function kpis(id,cards){$(id).innerHTML=cards.map(([name,value,note])=>`<div class="kpi"><div class="kpi-label">${esc(name)}</div><div class="kpi-value">${esc(typeof value==='number'?value.toLocaleString():value)}</div><div class="kpi-note">${esc(note)}</div></div>`).join('')}
function plot(id,traces,layout={}){let el=$(id);if(!el)return;if(!window.Plotly){el.innerHTML='<div class="empty">Charts require an internet connection to load Plotly.</div>';return;}let base={height:315,paper_bgcolor:'#fff',plot_bgcolor:'#fff',font:{family:'Inter, Segoe UI, Arial',size:11,color:'#65758c'},margin:{l:58,r:20,t:25,b:65},showlegend:false,hovermode:'closest',xaxis:{automargin:true},yaxis:{automargin:true}};Plotly.react(el,traces,{...base,...layout},{responsive:true,displayModeBar:false});}
function bar(id,entries,color='#3457b8',horizontal=false){if(!entries.length){$(id).innerHTML='<div class="empty">No records in the selected filters.</div>';return}let list=[...entries].reverse();plot(id,[horizontal?{type:'bar',orientation:'h',y:list.map(x=>pretty(x[0])),x:list.map(x=>x[1]),marker:{color},hovertemplate:'%{y}: %{x} sessions<extra></extra>'}:{type:'bar',x:list.map(x=>pretty(x[0])),y:list.map(x=>x[1]),marker:{color}}],horizontal?{margin:{l:165,r:18,t:12,b:44},yaxis:{automargin:true},xaxis:{title:'Sessions'}}:{})}
function miniList(id,entries,label=k=>k){let el=$(id);el.innerHTML=entries.length?entries.map(([k,n])=>`<div class="listrow"><span class="name">${esc(label(k))}</span><span class="amount">${Number(n).toLocaleString()}</span></div>`).join(''):'<div class="empty">No data available for this selection.</div>'}
function sessionList(id,rows,title,subtitle){$(id).innerHTML=rows.length?rows.map(r=>`<button class="session-row" data-key="${esc(r.source+'::'+r.id)}"><span class="snippet">${esc(title(r)||'No transcript available')}</span><span class="meta">${esc(subtitle(r))}</span></button>`).join(''):'<div class="empty">No matching sessions.</div>';$(id).querySelectorAll('[data-key]').forEach(el=>el.addEventListener('click',()=>openRecord(el.dataset.key)))}
function sessionTable(id,rows,columns){$(id).innerHTML=rows.length?`<table class="data-table"><thead><tr>${columns.map(c=>`<th>${esc(c[0])}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr data-key="${esc(r.source+'::'+r.id)}">${columns.map(c=>`<td>${esc(c[1](r))}</td>`).join('')}</tr>`).join('')}</tbody></table>`:'<div class="empty">No matching sessions.</div>';$(id).querySelectorAll('[data-key]').forEach(el=>el.addEventListener('click',()=>openRecord(el.dataset.key)))}
let currentPage='executive';function go(page){currentPage=page;document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id==='page-'+page));document.querySelectorAll('[data-page]').forEach(b=>{b.classList.toggle('active',b.dataset.page===page);b.setAttribute('aria-current',b.dataset.page===page?'page':'false')});render();window.scrollTo({top:0,behavior:'instant'})}
function populate(id,field){const sel=$(id);[...new Set(ALL.map(r=>r[field]).filter(Boolean))].sort().forEach(s=>{let o=document.createElement('option');o.value=s;o.textContent=id==='filter-topic'&&TOPICS[s]?`${s} · ${TOPICS[s]}`:pretty(s);sel.appendChild(o)})}
[['filter-source','source'],['filter-language','lang'],['filter-intent','intent'],['filter-sentiment','sent'],['filter-topic','topic']].forEach(x=>populate(...x));
function filterRows(){let search=$('filter-search').value.trim().toLowerCase(),s=$('filter-source').value,l=$('filter-language').value,i=$('filter-intent').value,t=$('filter-topic').value,sen=$('filter-sentiment').value,from=$('filter-from').value,to=$('filter-to').value;return ALL.filter(r=>(!s||r.source===s)&&(!l||r.lang===l)&&(!i||r.intent===i)&&(!t||r.topic===t)&&(!sen||r.sent===sen)&&(!from||r.date>=from)&&(!to||r.date<=to)&&(!search||(r.id+' '+r.text+' '+r.principalIssue).toLowerCase().includes(search)))}
function render(){let R=filterRows();$('scope').textContent=`${R.length.toLocaleString()} sessions · ${R.filter(r=>r.responded).length.toLocaleString()} with citizen input`;switch(currentPage){case'executive':renderExecutive(R);break;case'operations':renderOperations(R);break;case'behavior':renderBehavior(R);break;case'conversation':renderConversation(R);break;}}
function fact(label,value){return `<div class="fact"><small>${esc(label)}</small>${esc(value??'Unavailable')}</div>`}
function openRecord(key){
 let r=ALL.find(x=>x.source+'::'+x.id===key);if(!r)return;
 $('modal-title').textContent='Session · '+r.id;
 window.activeScoringSession=r;
 const details=[['Source',r.source],['Started',r.datetime?new Date(r.datetime).toLocaleString('en-MY',{dateStyle:'medium',timeStyle:'short'}):'Unavailable'],['Session language',r.lang],['Citizen messages',r.msgs],['Sentiment',pretty(r.sent)],['Intent',pretty(r.intent)],['Ministry topic',r.topic],['Scoring',r.scored?'Available':'Unavailable'],['Urgency route',r.urgencyRoute||'Unavailable']];
 const scoreCards=Object.entries(r.dimensions).map(([k,v])=>`<button type="button" class="score-card" data-dim="${esc(k)}"><span class="score-label">${esc(pretty(k))}</span><span class="score-number">${esc(validNum(v.score)?v.score.toFixed(2)+' / 5':v.status||'Unavailable')}</span><span class="score-hint">${esc(v.status||'Unavailable')} · Coverage ${validNum(v.coverage)?(v.coverage*100).toFixed(0)+'%':'—'} · Click for evidence and rationale</span></button>`).join('');
 const reviewNotes=[r.scoringReview?'<span class="detail-tag">Human-review flag</span>':'',r.coverageAudit?'<span class="detail-tag">Scoring coverage check</span>':''].join('');
 $('modal-body').innerHTML=`<div class="detail-grid compact-facts">${details.map(([a,b])=>fact(a,b)).join('')}</div><h4>Citizen conversation</h4><div class="pre">${esc(r.text||'No citizen messages recorded')}</div><h4>Principal issue</h4><div class="pre">${esc(r.principalIssue||'Not available')}</div><h4>Scoring and classification</h4>${reviewNotes}<p class="helper">Select a scoring dimension to examine recorded criterion-level evidence, rationale, and confidence.</p><div class="scoring-cards">${scoreCards}</div><div id="score-explanation" class="score-explanation" aria-live="polite"><p class="helper">Choose a dimension above to view its justification.</p></div><details class="optional-reply"><summary>Show system replies</summary><div class="pre">${esc(r.aiText||'Not available')}</div></details><p class="helper">These are model-generated assessments, not independently validated findings.</p>`;
 $('modal-body').querySelectorAll('[data-dim]').forEach(b=>b.onclick=()=>showDimension(b.dataset.dim));
 $('modal-shade').classList.add('open');document.body.classList.add('modal-open');
}
function showDimension(dim){
 const r=window.activeScoringSession;
 if(!r)return;
 const calculated=r.dimensions[dim]||{};
 let full={};try{full=JSON.parse(r.scoringFull||'{}')}catch(e){}
 const raw=(full.raw_ai_result||{})[dim]||{};
 const rawIndicators=Object.entries(raw).filter(([k,v])=>v&&typeof v==='object'&&!Array.isArray(v)&&('score' in v||'rationale' in v||'evidence_quotes' in v));
 const label=pretty(dim);
 const state=calculated.status||'Unavailable';
 const score=validNum(calculated.score)?calculated.score.toFixed(2)+' / 5':'Not scored';
 const coverage=validNum(calculated.coverage)?(calculated.coverage*100).toFixed(0)+'%':'Unavailable';
 const evidenceCards=rawIndicators.map(([key,v])=>{
   const quotes=Array.isArray(v.evidence_quotes)?v.evidence_quotes.filter(q=>String(q||'').trim()):[];
   const evidence=quotes.length?`<div class="evidence-row"><span class="field-name">Evidence:</span><div class="evidence-quotes">${quotes.map(q=>esc(q)).join('\n')}</div></div>`:'<div class="unavailable-row">No evidence quotation recorded.</div>';
   const rationale=v.rationale?`<div class="evidence-row"><span class="field-name">Why this score:</span> ${esc(v.rationale)}</div>`:'<div class="unavailable-row">No criterion rationale recorded.</div>';
   const confidence=v.confidence?`<div class="confidence-row">Confidence: ${esc(v.confidence)}</div>`:'';
   const scoreLabel=(v.score===null||v.score===undefined||String(v.score).trim()==='')?'NE':v.score;
   return `<article class="criterion-evidence-card"><h5>${esc(pretty(key))} · ${esc(scoreLabel)}</h5>${evidence}${rationale}${confidence}</article>`;
 }).join('');
 const notes=raw.overall_notes?`<div class="overall-notes"><span class="field-name">Overall notes:</span> ${esc(raw.overall_notes)}</div>`:'';
 const summaryReason=calculated.reason?`<p class="calculation-reason">${esc(calculated.reason)}</p>`:'';
 $('score-explanation').innerHTML=`<h4 class="dimension-heading">${esc(label)} — evidence and rationale</h4><p class="dimension-summary">${esc(state)} · ${esc(score)} · Coverage: ${esc(coverage)}</p>${summaryReason}<div class="criterion-list">${evidenceCards||'<div class="criterion-evidence-card">No criterion-level explanation was saved for this dimension.</div>'}</div>${notes}`;
 $('score-explanation').scrollIntoView({behavior:'smooth',block:'nearest'});
}
function closeModal(){$('modal-shade').classList.remove('open');document.body.classList.remove('modal-open')}
function exportRows(){let R=filterRows(),cols=['id','source','date','lang','responded','sent','intent','topic','msgs','scored','scoringReview','coverageAudit','text'];let csv=[cols.join(','),...R.map(r=>cols.map(k=>'"'+String(r[k]??'').replace(/"/g,'""')+'"').join(','))].join('\r\n');let a=document.createElement('a'),url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));a.href=url;a.download='dengar_filtered_sessions.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
['filter-source','filter-language','filter-intent','filter-sentiment','filter-topic','filter-from','filter-to'].forEach(id=>$(id).addEventListener('change',render));$('filter-search').addEventListener('input',render);$('journey-gap').addEventListener('change',render);$('reset').addEventListener('click',()=>{document.querySelectorAll('.toolbar select,.toolbar input').forEach(el=>el.value='');render()});$('export').addEventListener('click',exportRows);
document.querySelectorAll('[data-page]').forEach(el=>el.addEventListener('click',()=>go(el.dataset.page)));$('close-modal').addEventListener('click',closeModal);$('modal-shade').addEventListener('click',e=>{if(e.target===$('modal-shade'))closeModal()});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
render();
'''

EXTRA_JS = r'''
function enhancedExplorer(R){
 let S=R.filter(r=>r.responded&&r.scored).sort((a,b)=>b.datetime.localeCompare(a.datetime));
 const el=$('co-rows');if(!el)return;
 const pageSize=100;let slice=S.slice(0,pageSize);
 el.innerHTML=`<div class="explorer-wrap"><table class="explorer-table"><thead><tr><th>Session ID</th><th>Date</th><th>Dataset</th><th>Topic</th><th>Sentiment</th><th>Intent</th><th>Urgency</th><th>Human review</th><th>Principal issue</th></tr></thead><tbody>${slice.map(r=>`<tr data-key="${esc(r.source+'::'+r.id)}"><td class="short-id">${esc(r.id)}</td><td>${esc(r.date)}</td><td>${esc(r.source)}</td><td>${esc(r.topic)}</td><td><span class="status-pill ${esc(r.sent)}">${esc(pretty(r.sent))}</span></td><td>${esc(pretty(r.intent))}</td><td>${esc(pretty(r.urgencyRoute))}</td><td>${r.scoringReview?'Flagged':'No'}</td><td class="issue-cell">${esc(r.principalIssue||'Unavailable')}</td></tr>`).join('')}</tbody></table></div><p class="helper">Showing ${slice.length} of ${S.length} scored responding sessions. Narrow filters to inspect additional records.</p>`;
 el.querySelectorAll('[data-key]').forEach(e=>e.onclick=()=>openRecord(e.dataset.key));
}
const originalConversationRender=renderConversation;
renderConversation=function(R){originalConversationRender(R);enhancedExplorer(R)};
'''

CSS += r'''
.keyword-pill{cursor:pointer;font-family:inherit;transition:background .12s,border-color .12s}
.keyword-pill:hover,.keyword-pill:focus-visible{background:#eaf0fd;border-color:#96b0e1;outline:none}
.keyword-session-list{display:flex;flex-direction:column;gap:10px;max-height:58vh;overflow-y:auto;padding-right:5px}
.keyword-session{display:block;text-align:left;width:100%;border:1px solid #e0e7f3;border-radius:11px;background:#fff;padding:13px 15px;color:var(--ink);font-weight:400;overflow-wrap:anywhere}
.keyword-session:hover,.keyword-session:focus-visible{background:#f7f9fe;border-color:#9eb4e5;outline:none}
.keyword-session-head{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;color:#72809a;font-size:11px;margin-bottom:8px}
.keyword-session-text{display:block;white-space:pre-wrap;line-height:1.65;font-size:12px}
.keyword-session-issue{display:block;color:#63738d;font-size:11px;margin-top:9px;line-height:1.5}
.keyword-match{background:#fff1ad;color:#253754;border-radius:2px;padding:1px 2px}
'''

V4_JS = r'''
const mean=a=>a.length?a.reduce((s,v)=>s+v,0)/a.length:null;
const hrlabel=h=>h===0?'12 AM':h<12?`${h} AM`:h===12?'12 PM':`${h-12} PM`;
function closeSessionEvidence(){closeModal()}
function sessionClosing(r){
 if(!r.responded)return false;
 // Explicit courtesy closing, not successful resolution. Avoid matching thanks in opening sentences.
 let msgs=[];
 try{let t=JSON.parse(r.timeline||'[]');if(Array.isArray(t))msgs=t.map(m=>({role:m.role,content:String(m.content||'')}))}catch(e){}
 let lastU=''; let lastA='';
 if(msgs.length){for(let j=msgs.length-1;j>=0;j--){let m=msgs[j];if((m.role===0||m.role==='0')&&!lastU)lastU=m.content;if((m.role===1||m.role==='1')&&!lastA)lastA=m.content;if(lastU&&lastA)break}}
 if(!lastU){let t=(r.text||'').trim().split(/\n+/);lastU=t[t.length-1]||''}
 if(!lastA){let t=(r.aiText||'').trim().split(/\n+/);lastA=t[t.length-1]||''}
 const close=/\b(thank(?:s| you)|terima kasih|jumpa lagi|selamat tinggal|bye(?: bye)?|goodbye|appreciate (?:it|your help))\b/i;
 return !!(close.test(lastU.slice(-190))&&lastA.trim());
}
function trendRows(rows, grouping){
 const week=[...new Set(rows.map(r=>r.week).filter(Boolean))].sort();
 const labels=topCounts(rows,grouping,6).map(x=>x[0]);
 return {week,labels,traces:labels.map((v,i)=>({type:'scatter',mode:'lines+markers',name:pretty(v),x:week,y:week.map(w=>rows.filter(r=>r.week===w&&r[grouping]===v).length),line:{color:['#304fa6','#15936b','#bd8d3c','#9673ae','#cc596d','#6f8fbd'][i],width:2},hovertemplate:'%{x}<br>%{y} sessions<extra></extra>'}))};
}
function openTopic(topic){
 const src=filterRows().filter(r=>r.responded&&r.topic===topic);
 $('modal-title').textContent=TOPICS[topic]||topic;
 const last=src.map(r=>r.week).filter(Boolean).sort().slice(-1)[0];
 const allweeks=[...new Set(src.map(r=>r.week).filter(Boolean))].sort();
 const weekly=allweeks.map(w=>src.filter(r=>r.week===w).length);
 const latest=src.filter(r=>r.principalIssue||r.text).sort((a,b)=>b.datetime.localeCompare(a.datetime)).slice(0,30);
 let numKnown=src.filter(r=>['negative','positive','neutral','mixed'].includes(r.sent));
 let neg=numKnown.filter(r=>r.sent==='negative').length, pos=numKnown.filter(r=>r.sent==='positive').length;
 const kpisHTML=`<div class="topic-metrics"><div class="topic-metric">Sessions<strong>${src.length.toLocaleString()}</strong></div><div class="topic-metric">Negative sentiment<strong>${numKnown.length?pct(neg,numKnown.length).toFixed(1)+'%':'—'}</strong></div><div class="topic-metric">Positive sentiment<strong>${numKnown.length?pct(pos,numKnown.length).toFixed(1)+'%':'—'}</strong></div></div>`;
 const evidence=latest.map(r=>`<button class="topic-list-button" data-key="${esc(r.source+'::'+r.id)}">${esc(r.principalIssue||r.text.slice(0,170))}<small>${esc(r.date)} · ${esc(r.source)} · ${esc(pretty(r.sent))} · ${esc(pretty(r.intent))}</small></button>`).join('');
 $('modal-body').innerHTML=`<p class="helper">Current filters · Automatically assigned topic. Change is measured by recorded session counts, not government performance.</p>${kpisHTML}<h4>Weekly discussion volume</h4><div id="topic-deep-trend" class="topic-spark"></div><h4>What citizens are raising</h4><div class="list">${evidence||'<div class="empty">No issue-level text available</div>'}</div><button type="button" class="smallbtn" id="topic-filter-button">Filter dashboard to this topic</button>`;
 $('modal-body').querySelectorAll('[data-key]').forEach(el=>el.onclick=()=>openRecord(el.dataset.key));
 $('topic-filter-button').onclick=()=>{closeModal();$('filter-topic').value=topic;render()};
 $('modal-shade').classList.add('open');document.body.classList.add('modal-open');
 plot('topic-deep-trend',[{type:'scatter',mode:'lines+markers',x:allweeks,y:weekly,line:{color:'#2f51ad',width:2.5},marker:{size:7},hovertemplate:'%{x}<br>%{y} sessions<extra></extra>'}],{height:245,margin:{l:45,r:18,t:15,b:42},yaxis:{title:'Sessions',rangemode:'tozero'},xaxis:{automargin:true}});
}
// Show exactly which sessions the topic model assigned to this keyword.
// A model keyword need not appear verbatim in the citizen's text.
function keywordSessionMatch(r, keyword){
 return (r.keywords||'').split(/[,;|]+/).some(t=>t.trim().toLocaleLowerCase()===keyword.toLocaleLowerCase());
}
function highlightKeywordExcerpt(value, keyword){
 const text=String(value||'');
 const pos=text.toLocaleLowerCase().indexOf(keyword.toLocaleLowerCase());
 if(pos<0)return '';
 const start=Math.max(0,pos-105),end=Math.min(text.length,pos+keyword.length+150);
 const before=text.slice(start,pos),match=text.slice(pos,pos+keyword.length),after=text.slice(pos+keyword.length,end);
 return `${start?'…':''}${esc(before)}<mark class="keyword-match">${esc(match)}</mark>${esc(after)}${end<text.length?'…':''}`;
}
function openKeyword(keyword){
 const matches=filterRows().filter(r=>r.responded&&keywordSessionMatch(r,keyword))
   .sort((a,b)=>(b.datetime||'').localeCompare(a.datetime||''));
 const verbatim=matches.filter(r=>(r.text||'').toLocaleLowerCase().includes(keyword.toLocaleLowerCase())).length;
 $('modal-title').textContent=`Keyword: ${keyword}`;
 const list=matches.map(r=>{
   const snippet=highlightKeywordExcerpt(r.text,keyword);
   const found=!!snippet;
   const description=snippet||esc((r.text||'').slice(0,230)||'No citizen text available');
   return `<button type="button" class="keyword-session" data-key="${esc(r.source+'::'+r.id)}">
     <span class="keyword-session-head"><span>${esc(r.date||'Unknown date')} · ${esc(r.source)} · ${esc(pretty(r.sent))}</span><span>${found?'Exact text match':'Model keyword only'}</span></span>
     <span class="keyword-session-text">${description}</span>
     ${r.principalIssue&&r.principalIssue!=='Unavailable'?`<span class="keyword-session-issue">Principal issue: ${esc(r.principalIssue.slice(0,210))}</span>`:''}
   </button>`;
 }).join('');
 $('modal-body').innerHTML=`<p class="helper">Showing all ${matches.length.toLocaleString()} responding sessions tagged with this model-extracted keyword under the current dashboard filters. A topic keyword may be related to the conversation without appearing literally in the transcript.</p>
  <div class="topic-metrics"><div class="topic-metric">Tagged sessions<strong>${matches.length.toLocaleString()}</strong></div><div class="topic-metric">Exact text matches<strong>${verbatim.toLocaleString()}</strong></div><div class="topic-metric">Tag only<strong>${(matches.length-verbatim).toLocaleString()}</strong></div></div>
  <h4>Sessions and evidence</h4><div class="keyword-session-list">${list||'<div class="empty">No sessions for this keyword.</div>'}</div>`;
 $('modal-body').querySelectorAll('[data-key]').forEach(el=>el.onclick=()=>openRecord(el.dataset.key));
 $('modal-shade').classList.add('open');document.body.classList.add('modal-open');
}
function renderExecutiveV4(R){
 renderExecutiveOriginal(R);
 const E=R.filter(r=>r.responded);
 const agenda=E.filter(r=>r.principalIssue&&r.principalIssue!=='Unavailable').sort((a,b)=>b.datetime.localeCompare(a.datetime));
 const topics=[...new Set(agenda.map(r=>r.topic))].filter(t=>validTopic(t));
 let recent=[];
 for(const t of topics){let g=agenda.filter(r=>r.topic===t);let neg=g.find(r=>r.sent==='negative'),pos=g.find(r=>r.sent==='positive');recent.push(neg||pos||g[0]);if(recent.length===6)break}
 if(recent.length<6){for(let r of agenda){if(recent.length===6)break;if(!recent.includes(r))recent.push(r)}}
 $('ex-agenda').innerHTML=recent.map(r=>`<button class="agenda-card ${esc(r.sent)}" data-key="${esc(r.source+'::'+r.id)}"><span class="agenda-name">${esc(r.principalIssue.slice(0,125))}</span><span class="issue-preview">${esc(TOPICS[r.topic]||r.topic)} · ${esc(pretty(r.intent))}</span><span class="agenda-code">${esc(r.date)} · ${esc(r.source)}</span><span class="sent-marker">${esc(pretty(r.sent))}${validNum(r.sentimentScore)?' · '+r.sentimentScore.toFixed(2):''}</span></button>`).join('')||'<div class="empty">No scored principal issues available for these filters.</div>';
 $('ex-agenda').querySelectorAll('[data-key]').forEach(el=>el.onclick=()=>openRecord(el.dataset.key));
 const words={};E.forEach(r=>{const seen=new Set((r.keywords||'').split(/[,;|]+/).map(x=>x.trim()).filter(x=>x&&!['unavailable','unknown','unassigned'].includes(x.toLowerCase())));seen.forEach(w=>words[w]=(words[w]||0)+1)});
 $('ex-keywords').innerHTML=Object.entries(words).sort((a,b)=>b[1]-a[1]).slice(0,22).map(([w,n])=>`<button type="button" class="keyword-pill" data-keyword="${esc(w)}" title="View sessions tagged with this keyword">${esc(w)} <small>${n}</small></button>`).join('')||'<div class="empty">No extracted keywords available.</div>';
 $('ex-keywords').querySelectorAll('[data-keyword]').forEach(button=>button.onclick=()=>openKeyword(button.dataset.keyword));
 let T=topCounts(E.filter(r=>validTopic(r.topic)),'topic',10);
 const max=Math.max(1,...T.map(x=>x[1]));
 $('ex-topics').innerHTML=T.map(([t,n])=>`<button type="button" class="topic-list-button" data-topic="${esc(t)}">${esc(TOPICS[t]||t)}<small>${n} sessions · ${pct(n,E.length).toFixed(1)}% of responding sessions · View details</small><div class="metric-track" style="margin-top:7px"><span style="width:${100*n/max}%"></span></div></button>`).join('')||'<div class="empty">No assigned topics in selection.</div>';
 $('ex-topics').querySelectorAll('[data-topic]').forEach(el=>el.onclick=()=>openTopic(el.dataset.topic));
}
const renderExecutiveOriginal=renderExecutive; renderExecutive=renderExecutiveV4;
function renderOperationsV4(R){
 const E=R.filter(r=>r.responded),dur=R.map(r=>r.duration).filter(n=>validNum(n)&&n>=0);
 const finished=E.filter(sessionClosing);
 kpis('op-kpis',[
 ['Total sessions',R.length,'Unique source and session ID'],
 ['Citizen participation',pct(E.length,R.length).toFixed(1)+'%',`${E.length} sessions with citizen input`],
 ['Average recorded duration',dur.length?(mean(dur)/60).toFixed(2)+' min':'—','Mean of valid start-to-end intervals'],
 ['Explicit closing rate',E.length?pct(finished.length,E.length).toFixed(1)+'%':'—',`${finished.length} conversations with closing phrase and recorded AI reply; heuristic, not resolution`]]);
 const weeks=[...new Set(R.map(r=>r.week).filter(Boolean))].sort();
 const counted=weeks.map(w=>{let rows=R.filter(r=>r.week===w);return {w,n:rows.length,p:pct(rows.filter(r=>r.responded).length,rows.length)}});
 // Explicitly separate participation rate from session counts to avoid misreading a dual-axis overlay.
 plot('op-week',[
 {type:'bar',name:'All sessions',x:weeks,y:counted.map(x=>x.n),marker:{color:'#4a69b8'},hovertemplate:'%{x}<br>%{y} sessions<extra></extra>'},
 {type:'scatter',name:'Participation rate',mode:'lines+markers',x:weeks,y:counted.map(x=>x.p),xaxis:'x2',yaxis:'y2',line:{color:'#15936b',width:2.5},hovertemplate:'%{x}<br>%{y:.1f}% participated<extra></extra>'}
 ],{height:350,grid:{rows:2,columns:1,pattern:'independent',roworder:'top to bottom'},xaxis:{showticklabels:false},xaxis2:{title:'Week',tickangle:-20},yaxis:{title:'Sessions',domain:[.42,1],rangemode:'tozero'},yaxis2:{title:'Rate (%)',domain:[0,.31],range:[0,100],ticksuffix:'%'},margin:{l:60,r:20,t:25,b:55},legend:{orientation:'h',y:1.13},showlegend:true});
 const days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],hrs=Array.from({length:24},(_,i)=>i),labels=hrs.map(hrlabel);
 const cells=days.map(d=>hrs.map(h=>{let a=R.filter(r=>r.weekday===d&&r.hour===h);return {n:a.length,yes:a.filter(r=>r.responded).length}}));
 plot('op-heat',[{type:'heatmap',x:labels,y:days,z:cells.map(z=>z.map(c=>c.n?pct(c.yes,c.n):null)),customdata:cells.map(z=>z.map(c=>[c.n,c.yes])),colorscale:[[0,'#f0f3fa'],[1,'#287fbd']],zmin:0,zmax:100,colorbar:{title:'%'},hovertemplate:'%{y} · %{x}<br>Sessions: %{customdata[0]}<br>Responding: %{customdata[1]}<br>Rate: %{z:.1f}%<extra></extra>'}],{height:360,margin:{l:92,r:55,t:10,b:65},xaxis:{tickangle:-50,dtick:2},yaxis:{autorange:'reversed'}});
 const sources=topCounts(R,'source',12);plot('op-source',[{type:'bar',x:sources.map(x=>x[0]),y:sources.map(([s])=>pct(R.filter(r=>r.source===s&&r.responded).length,R.filter(r=>r.source===s).length)),text:sources.map(([s,n])=>`n=${n}`),textposition:'outside',marker:{color:'#3457b8'},hovertemplate:'%{x}<br>%{y:.1f}% participation<extra></extra>'}],{yaxis:{title:'Participation (%)',range:[0,100]},margin:{l:55,r:20,t:45,b:50}});
 plot('op-hour',[{type:'bar',x:labels,y:hrs.map(h=>R.filter(r=>r.hour===h).length),marker:{color:'#7895c9'},hovertemplate:'%{x}<br>%{y} sessions<extra></extra>'}],{xaxis:{tickangle:-45,dtick:2},yaxis:{title:'Sessions'},margin:{l:55,r:20,t:20,b:72}});
 miniList('op-quality',[['Data/cleaning review flags',R.filter(r=>r.cleaningReview).length],['Overlapping recorded sessions',R.filter(r=>r.overlap).length],['Missing/invalid session duration',R.filter(r=>!validNum(r.duration)).length],['No citizen response',R.length-E.length],['Missing session start',R.filter(r=>!r.datetime).length]],k=>k);
}
renderOperations=renderOperationsV4;
function renderBehaviorV4(R){
 const limit=Number($('journey-gap').value),E=R.filter(r=>r.responded), allGaps=R.map(r=>r.gapPrev).filter(n=>validNum(n)&&n>=0);
 // the threshold is cumulative for adjacency selection, but the histogram bins are mutually exclusive.
 const A=R.filter(r=>validNum(r.gapPrev)&&r.gapPrev>=0&&r.gapPrev<=limit&&r.prevId&&r.prevId!=='Unavailable');
 const afterEmpty=A.filter(r=>r.prevEng==='no_user_response'&&r.responded);
 const complete=E.filter(sessionClosing);
 kpis('be-kpis',[
 ['Nearby session pairs',A.length,`Adjacent starts within ${limit} seconds; not unique visitors`],
 ['Citizen input after no-response session',afterEmpty.length,'Nearby next sessions containing user input; not verified retries'],
 ['Explicit closing conversations',E.length?pct(complete.length,E.length).toFixed(1)+'%':'—',`${complete.length} of ${E.length} responding sessions; heuristic only`],
 ['Average start gap',allGaps.length?mean(allGaps).toFixed(1)+' sec':'—','Arithmetic mean of valid start-to-start gaps']]);
 const names={no_user_response:'No response',one_user_message:'One message',multiple_user_messages:'Multiple messages'};
 bar('be-transition',topCounts(A,r=>`${names[r.prevEng]||r.prevEng} → ${names[r.engagement]||r.engagement}`,10),'#3457b8',true);
 const bands=[['0–30 sec',0,30],['>30–60 sec',30,60],['>60–120 sec',60,120],['>120–180 sec',120,180],['>180–300 sec',180,300],['>300–600 sec',300,600],['>600 sec',600,Infinity]];
 plot('be-gaps',[{type:'bar',x:bands.map(x=>x[0]),y:bands.map(([n,lo,hi],i)=>allGaps.filter(v=>i===0?v>=0&&v<=hi:v>lo&&v<=hi).length),marker:{color:'#7f9bd0'},hovertemplate:'%{x}<br>%{y} pairs<extra></extra>'}],{height:320,yaxis:{title:'Adjacent session pairs'},xaxis:{tickangle:-25},margin:{l:52,r:15,t:14,b:92}});
 const groups=[['1 message',n=>n===1],['2 messages',n=>n===2],['3–4 messages',n=>n>=3&&n<=4],['5+ messages',n=>n>=5]];
 plot('be-depth',[{type:'bar',x:groups.map(x=>x[0]),y:groups.map(x=>E.filter(r=>x[1](r.msgs)).length),marker:{color:'#15936b'}}],{yaxis:{title:'Responding sessions'}});
 miniList('be-language',[['Language changed from preceding session',A.filter(r=>r.languageChanged).length],['More than one writing script',E.filter(r=>r.scriptsMixed).length],['Tamil script',E.filter(r=>r.tamilScript).length],['Arabic script',E.filter(r=>r.arabicScript).length],['Chinese script',E.filter(r=>r.cjkScript).length]],x=>x);
 sessionTable('be-rows',A.filter(r=>r.responded).sort((a,b)=>a.gapPrev-b.gapPrev).slice(0,100),[['Dataset',r=>r.source],['Started',r=>r.datetime.slice(0,19).replace('T',' ')],['Previous',r=>pretty(r.prevEng)],['Current',r=>pretty(r.engagement)],['Start gap (sec)',r=>r.gapPrev.toFixed(1)],['Language',r=>r.lang]]);
}
renderBehavior=renderBehaviorV4;
const originalConversationV4=renderConversation;
function renderConversationV4(R){
 originalConversationV4(R);
 const E=R.filter(r=>r.responded),S=E.filter(r=>r.scored);
 const w=trendRows(E,'intent');plot('co-intent-trend',w.traces,{height:335,showlegend:true,legend:{orientation:'h',y:-.24},margin:{l:55,r:22,t:18,b:88},yaxis:{title:'Responding sessions',rangemode:'tozero'},xaxis:{tickangle:-25}});
 const t=topCounts(E.filter(r=>validTopic(r.topic)),'topic',9).map(x=>x[0]);const ints=topCounts(E,'intent',7).map(x=>x[0]);
 const topicAssoc=[];for(let topic of t)for(let intent of ints){let count=E.filter(r=>r.topic===topic&&r.intent===intent).length;if(count)topicAssoc.push({topic,intent,count})}
 plot('co-topic-assoc',[{type:'scatter',mode:'markers',x:topicAssoc.map(x=>pretty(x.intent)),y:topicAssoc.map(x=>TOPICS[x.topic]||x.topic),marker:{size:topicAssoc.map(x=>8+Math.sqrt(x.count)*4),sizemode:'diameter',color:'#4364b6',opacity:.73,line:{color:'#fff',width:1}},customdata:topicAssoc.map(x=>x.count),hovertemplate:'%{y}<br>%{x}<br>%{customdata} sessions<extra></extra>'}],{height:370,margin:{l:160,r:18,t:20,b:100},xaxis:{tickangle:-28},yaxis:{automargin:true}});
 const labels=['negative','neutral','positive','mixed'],ia=[];for(let intent of ints)for(let sent of labels){let count=E.filter(r=>r.intent===intent&&r.sent===sent).length;if(count)ia.push({intent,sent,count})}
 plot('co-intent-assoc',[{type:'scatter',mode:'markers',x:ia.map(x=>pretty(x.sent)),y:ia.map(x=>pretty(x.intent)),customdata:ia.map(x=>x.count),marker:{size:ia.map(x=>8+Math.sqrt(x.count)*4),sizemode:'diameter',color:ia.map(x=>x.sent==='negative'?'#d5616e':x.sent==='positive'?'#15936b':'#8a9bb8'),opacity:.72},hovertemplate:'%{y} · %{x}<br>%{customdata} sessions<extra></extra>'}],{height:360,margin:{l:165,r:18,t:22,b:65}});
 const dims=['issue_clarity','evidence_strength','impact_severity','request_actionability','urgency'];const levels=['Very low','Low','Moderate','Strong','Very strong'];
 const bins=[v=>v>=1&&v<2,v=>v>=2&&v<3,v=>v>=3&&v<4,v=>v>=4&&v<4.5,v=>v>=4.5&&v<=5];
 plot('co-strength',levels.map((l,i)=>({type:'bar',orientation:'h',name:l,y:dims.map(pretty),x:dims.map(d=>S.filter(r=>validNum(r.dimensions[d]?.score)&&bins[i](r.dimensions[d].score)).length),marker:{color:['#abb9ca','#90a5c3','#7496c9','#4c78b7','#177f77'][i]}})),{height:370,barmode:'stack',showlegend:true,legend:{orientation:'h',y:-.2},margin:{l:175,r:15,t:20,b:92},xaxis:{title:'Numeric scored sessions'}});

}
renderConversation=renderConversationV4;
render();
'''

def main():
    parser=argparse.ArgumentParser(description='Generate modular DENGAR dashboard from analyzed master CSV')
    parser.add_argument('--input',default='analyzed.csv')
    parser.add_argument('--output',default='dengar_conversation_dashboard.html')
    parser.add_argument('--no-open',action='store_true')
    args,_=parser.parse_known_args()
    source=Path(args.input)
    if not source.is_file() and args.input=='output data/analyzed.csv' and Path('analyzed.csv').is_file():
        source=Path('analyzed.csv')
    if not source.is_file():
        raise FileNotFoundError(f'Cannot find {source.resolve()}; pass --input with the CSV path.')
    df=pd.read_csv(source,low_memory=False,encoding='utf-8-sig')
    records=build_records(df)
    data=json.dumps(records,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    head='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DENGAR Intelligence | Dashboard</title><script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script><style>'''
    body='''</style></head><body><header><div class="header-inner"><div><div class="brand">DENGAR<span>·</span>AI</div><div class="brand-sub">Citizen voice intelligence · Malaysia</div></div><nav class="nav" aria-label="Current dashboard"><button data-page="conversation" class="active">Conversation &amp; AI scoring</button></nav></div></header><main><div class="toolbar"><input id="filter-search" type="search" placeholder="Search session ID, transcript or issue..."><select id="filter-source"><option value="">All sources</option></select><select id="filter-language"><option value="">All languages</option></select><select id="filter-intent"><option value="">All intents</option></select><select id="filter-sentiment"><option value="">All sentiments</option></select><select id="filter-topic"><option value="">All topics</option></select><input id="filter-from" type="date" title="From date"><input id="filter-to" type="date" title="To date"><button id="reset">Reset</button><button id="export">Export CSV</button></div><div class="helper" id="scope"></div>'''
    foot='''<div class="footer">DENGAR Intelligence · Internal research report · One row per source/session. Classified topics and AI rubric scores are unverified. Session timing and language signals cannot establish unique-visitor identity. · Static HTML snapshot.</div></main><div id="modal-shade" class="modal-shade" role="dialog" aria-modal="true"><div class="modal"><div class="modal-head"><h3 id="modal-title">Session details</h3><button class="smallbtn" id="close-modal">Close</button></div><div id="modal-body"></div></div></div><script>'''
    js=(JS+EX_JS+OP_JS+BE_JS+CO_JS+EXTRA_JS+V4_JS+"\ngo('conversation');\n").replace('__DATA__',data).replace('__TOPICS__',json.dumps(TOPICS))
    html=head+CSS+body+EX_HTML+OP_HTML+BE_HTML+CO_HTML+foot+js+'</script></body></html>'
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(html,encoding='utf-8')
    print(f'Generated: {dest.resolve()}');print(f'Sessions: {len(records):,} | Scored: {sum(x["scored"] for x in records):,}')
    if not args.no_open:
        try:webbrowser.open(dest.resolve().as_uri())
        except Exception:pass

if __name__=='__main__':main()
