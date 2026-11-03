"""Home Minister citizen-voice rubric scoring (post sentiment/topic stage).

Install: pip install pandas openai pydantic
Run: python 03_home_minister_scoring.py --input-dir "output data" --batch-size 8
Requires OPENAI_API_KEY. API scoring is paid and can be time consuming.

Reads **/*[cleaned].csv; preserves all existing columns and rows, adds hm_ columns.
Creates one session-summary CSV and scored JSONL beside each cleaned CSV.
Do not treat AI outputs as verified allegations or emergency dispatch.
"""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field
from openai import OpenAI

VERSION = 'Home Minister rubric 2026 / four dimensions + urgency v1'
Score = Literal['1','2','3','4','5','NE','IE']
Confidence = Literal['High','Moderate','Low','Insufficient']
Gate = Literal['1','0','NE','IE']

TOPICS = {'POL':'Policing and community safety','IMM':'Immigration and borders',
          'JPN':'MyKad and civil registration','CYB':'Scams and cybercrime',
          'FWK':'Foreign workers','GFB':'General Home Ministry feedback',
          'OTH':'Other Home Ministry-related matter'}

WEIGHTS = {
 'issue_clarity': {'main_issue_identification':.25,'precise_identification':.20,
                   'consistent_terminology':.15,'coherent_sequencing':.15,
                   'boundary_definition':.15,'adaptive_clarification_resolution':.10},
 'evidence_strength': {'evidence_basis_directness':.25,'incident_specificity':.25,
                       'traceability_supporting_evidence':.30,'claim_evidence_alignment':.20},
 'impact_severity': {'functional_disruption':.30,'magnitude_of_harm':.35,
                     'scope_of_impact':.15,'duration_recoverability':.20},
 'request_actionability': {'desired_outcome_identification':.30,'request_specificity':.25,
                          'issue_request_alignment':.25,'administrative_actionability':.20},
 'urgency': {'immediacy_time_sensitivity':.35,'ongoing_exposure_escalation':.30,
             'vulnerability_protective_need':.20,'threat_specificity_actionability':.15}}

class Indicator(BaseModel):
    score: Score
    evidence_quotes: list[str] = Field(default_factory=list)
    rationale: str
    confidence: Confidence
    material_ie: bool = False

class DimensionControl(BaseModel):
    defensible_overall_result: bool
    insufficiency_reason: str | None = None

class IssueClarity(BaseModel):
    main_issue_identification: Indicator
    precise_identification: Indicator
    consistent_terminology: Indicator
    coherent_sequencing: Indicator
    boundary_definition: Indicator
    adaptive_clarification_resolution: Indicator
    control: DimensionControl
    overall_notes: str

class EvidenceStrength(BaseModel):
    evidence_basis_directness: Indicator
    incident_specificity: Indicator
    traceability_supporting_evidence: Indicator
    claim_evidence_alignment: Indicator
    control: DimensionControl
    overall_notes: str

class ImpactSeverity(BaseModel):
    functional_disruption: Indicator
    magnitude_of_harm: Indicator
    scope_of_impact: Indicator
    duration_recoverability: Indicator
    essential_function_access_blocked: bool
    no_meaningful_alternative: bool
    direct_catastrophic_consequence: bool
    severe_magnitude_ie_due_system_failure: bool
    control: DimensionControl
    overall_notes: str

RequestGateway = Literal['CONTINUE','NE','IE','NO_REQUEST_SOUGHT','NO_IDENTIFIABLE_OUTCOME']
class RequestActionability(BaseModel):
    citizen_request: str | None
    request_gateway: RequestGateway
    request_gateway_reason: str
    desired_outcome_identification: Indicator
    request_specificity: Indicator
    issue_request_alignment: Indicator
    administrative_actionability: Indicator
    control: DimensionControl
    overall_notes: str

class Urgency(BaseModel):
    immediacy_time_sensitivity: Indicator
    ongoing_exposure_escalation: Indicator
    vulnerability_protective_need: Indicator
    threat_specificity_actionability: Indicator
    gate_life_injury: Gate
    gate_violence_weapon: Gate
    gate_self_harm: Gate
    gate_child_dependent_abuse: Gate
    gate_abduction_trafficking: Gate
    gate_public_safety: Gate
    gate_fire_structural_environment: Gate
    gate_other_approved: Gate
    currently_exposed_vulnerable_people: bool
    high_impact_active_serious_harm: bool
    confidence: Confidence
    rationale: str
    control: DimensionControl

class RawSession(BaseModel):
    principal_issue: str
    validated_topic_code: Literal['POL','IMM','JPN','CYB','FWK','GFB','OTH','Unclear']
    topic_rationale: str
    issue_clarity: IssueClarity
    evidence_strength: EvidenceStrength
    impact_severity: ImpactSeverity
    request_actionability: RequestActionability
    urgency: Urgency
    human_review_required: bool
    human_review_reason: str | None

INSTRUCTIONS = '''You are a careful analyst of one five-minute Home Ministry (KDN) citizen listening session.
Apply the supplied Home Minister rubric only; do not use Hello JCorp scoring and DO NOT score sentiment or confirmation.
Unit of analysis: ONE principal issue per session. Select the principal citizen concern; do not treat AI/avatar prompts as citizen testimony. Only exact citizen utterances can appear in evidence_quotes. If no user message or no identifiable issue, clearly mark NE/IE instead of inventing details. Respect context, Malay/English/Tamil/multilingual wording. Do not treat speech fluency, accent, emotion, beliefs, government criticism or unfamiliar terminology as score determinants.

Topic codes: POL policing/safety; IMM immigration/borders; JPN MyKad/civil registration; CYB scams/cybercrime; FWK foreign workers; GFB general Home Ministry feedback; OTH other Home Ministry matter. If no defensible code, Unclear. A machine-assigned upstream topic is contextual and may be wrong.

All 1-5 indicators: 1 absent/very poor AFTER fair opportunity; 2 limited/vague; 3 partial/moderate; 4 clear/strong; 5 very clear/specific/strong. Assign NE when not elicited, not applicable, or no fair opportunity; IE when transcript/translation/system quality prevents fair interpretation. Explain each indicator with direct exact quotes, or state no supporting quotation. material_ie TRUE only when ambiguous information could materially change final decision. No invented documents, numbers, times, locations, risk, severity or request.

ISSUE CLARITY indicators: main_issue_identification (principal concern identifiable), precise_identification (service/entity/place/time/reference), consistent_terminology (coherent logical synonyms; NE if only brief mention), coherent_sequencing (NE if no sequence relevant), boundary_definition (principal vs secondary), adaptive_clarification_resolution (NE if no suitable probe). Distinguish intelligibility from truth, seriousness, emotion.
EVIDENCE STRENGTH: evidence_basis_directness (first-hand vs hearsay), incident_specificity (concrete event), traceability_supporting_evidence (locatable/checkable detail, not necessarily documents), claim_evidence_alignment (claim proportionate to supporting information). First-hand testimony is not proof. A severe allegation can have weak evidence.
IMPACT SEVERITY: functional_disruption (actual reported function/service impact), magnitude_of_harm (consequence not angry tone), scope_of_impact (number of identifiable affected people not complaint counts), duration_recoverability (NE if undiscussed/nonapplicable). Evaluate actual reported impact separately from hypothetical worst case. Set override booleans ONLY if transcript affirmatively supports them; severe_magnitude_ie_due_system_failure only for severe signal with uninterpretably corrupted magnitude.
REQUEST ACTIONABILITY: Determine if a fair opportunity to request occurred, including spontaneous request. If no opportunity and no spontaneous request -> gateway NE. If asked but response uninterpretable -> IE. If asked and explicit no request wanted -> NO_REQUEST_SOUGHT. If fair opportunity yet no identifiable outcome -> NO_IDENTIFIABLE_OUTCOME. Otherwise CONTINUE. Assess desired_outcome_identification, request_specificity, issue_request_alignment, administrative_actionability. Information/status enquiries CAN be actionable. Do not invent an implementation plan or demand citizen provide a budget. If no identifiable request after fair opportunity, desired_outcome_identification=1 and other indicators=NE.
URGENCY AND ESCALATION: imminence/time sensitivity; ongoing harmful exposure/escalation; vulnerability/protection need (vulnerability ALONE not Critical); threat specificity/actionability. Each 1-5 / NE / IE. Distinguish historical from current/imminent. Assess 8 critical gates separately: 1 only for concrete credible CURRENT/IMMINENT emergency, 0 if assessed and absent, NE if no relevant signal, IE if potential signal is uninterpretable. Gates: imminent death/serious injury, active violence/weapons, immediate self-harm, active severe child/dependent abuse, active abduction/confinement/trafficking, immediate public-safety threat, active fire/structural/environmental serious danger, other formally approved emergency (never improvise an approval). A critical route needs gate=1. Use human review for material IE or urgent safety indications; AI must not represent itself as dispatching responders.
Give concise and specific rationale for EVERY score, especially all 1/5 and NE/IE. Confidence means confidence in extraction/scoring, NOT confidence a claim is true. If short or poor-quality transcript, explicitly note limitations. Do not use sentiment or confirmation as dimensions.'''

LEVELS = {
 'issue_clarity':['Unclear','Limited clarity','Partly clear','Clear','Highly clear'],
 'evidence_strength':['Very weak','Weak','Moderate','Strong','Very strong'],
 'impact_severity':['Minimal','Limited','Material','Serious','Extreme'],
 'request_actionability':['No usable request','Weakly actionable','Partly actionable','Actionable','Highly actionable']}

def level(score, names):
    if score is None: return 'Not scoreable'
    return names[0 if score<1.5 else 1 if score<2.5 else 2 if score<3.5 else 3 if score<4.5 else 4]

def composite(dim, weights):
    reasons=[]; available={}
    for key,w in weights.items():
        indicator=getattr(dim,key)
        if indicator.score=='IE':
            reasons.append(('Material' if indicator.material_ie else 'Non-material')+' IE: '+key)
            if indicator.material_ie:
                return {'status':'IE','score':None,'coverage':None,'review':True,'reason':'; '.join(reasons)}
        if indicator.score.isdigit(): available[key]=(int(indicator.score),w)
    if not dim.control.defensible_overall_result:
        return {'status':'NE','score':None,'coverage':sum(w for _,w in available.values()),'review':False,'reason':dim.control.insufficiency_reason or 'Insufficient scoreable evidence'}
    if not available:
        return {'status':'NE','score':None,'coverage':0,'review':False,'reason':'No scoreable indicators'}
    denom=sum(w for _,w in available.values())
    score=sum(v*w for v,w in available.values())/denom
    return {'status':'SCORED','score':round(score,2),'coverage':round(denom,2),'review':bool(reasons),'reason':'; '.join(reasons)}

def finish(raw):
    all_dims={k:composite(getattr(raw,k),WEIGHTS[k]) for k in WEIGHTS}
    ic=all_dims['issue_clarity']; main=raw.issue_clarity.main_issue_identification.score
    if ic['score'] is not None:
        if main=='1': ic['score']=1.; ic['gateway']='Main issue identification=1'
        elif main=='2': ic['score']=min(ic['score'],3.); ic['gateway']='Main issue identification=2; cap 3'
    imp=all_dims['impact_severity']; i=raw.impact_severity
    if i.severe_magnitude_ie_due_system_failure:
        imp.update(status='IE',score=None,review=True,reason='Severe magnitude IE from system/translation failure')
    if imp['score'] is not None:
        floor=imp['score']; override=[]
        mag=i.magnitude_of_harm.score; fd=i.functional_disruption.score; dur=i.duration_recoverability.score
        if mag=='5': floor=max(floor,4.); override.append('Magnitude=5')
        if fd=='5' and i.essential_function_access_blocked: floor=max(floor,4.);override.append('Essential access blocked')
        if mag=='5' and dur=='5': floor=max(floor,4.5);override.append('Magnitude=5 and duration=5')
        if fd=='5' and mag in ('4','5') and i.no_meaningful_alternative:floor=max(floor,4.5);override.append('Severe functional blockage without alternative')
        if i.direct_catastrophic_consequence:floor=5.;override.append('Direct catastrophic consequence')
        imp['score']=round(floor,2); imp['override']='; '.join(override)
    req=all_dims['request_actionability']; rg=raw.request_actionability.request_gateway
    if rg in ('NE','IE','NO_REQUEST_SOUGHT'):
        req.update(status=rg,score=None,review=rg=='IE',reason=raw.request_actionability.request_gateway_reason)
    elif rg=='NO_IDENTIFIABLE_OUTCOME':
        req.update(status='SCORED',score=1.,reason='No identifiable request after fair opportunity')
    urg=all_dims['urgency']; u=raw.urgency
    gates={n:getattr(u,n) for n in ['gate_life_injury','gate_violence_weapon','gate_self_harm','gate_child_dependent_abuse','gate_abduction_trafficking','gate_public_safety','gate_fire_structural_environment','gate_other_approved']}
    triggered=[n for n,v in gates.items() if v=='1']
    route='NE'
    if triggered:route='Critical'
    elif any(v=='IE' for v in gates.values()): route='IE-Human Review';urg['review']=True
    elif urg['score'] is not None:
        v=urg['score'];route='Normal' if v<2 else 'Priority' if v<3.25 else 'Urgent'
        a=u.immediacy_time_sensitivity.score;b=u.ongoing_exposure_escalation.score;c=u.vulnerability_protective_need.score
        nums=[int(x) if x.isdigit() else 0 for x in (a,b,c)];a1,b1,c1=nums
        if a1==5 or b1==5 or (a1>=4 and b1>=3) or (b1>=4 and c1>=3) or (c1>=4 and u.currently_exposed_vulnerable_people): route='Urgent'
        if u.high_impact_active_serious_harm and route=='Normal':route='Priority'
    elif urg['status']=='IE':route='IE-Human Review'
    urg['route']=route;urg['critical_gates']=gates
    review=raw.human_review_required or any(d['review'] for d in all_dims.values()) or route in ('Urgent','Critical','IE-Human Review')
    return {'dimensions':all_dims,'human_review_required':review,'review_reason':raw.human_review_reason or '; '.join(d['reason'] for d in all_dims.values() if d['review']) or (route+' route' if route in ('Urgent','Critical','IE-Human Review') else '' )}

def safe_text(s):
    if s is None:return ''
    return str(s).strip()

def get_content(group):
    """Return citizen text, count and role-labelled conversation for fair-opportunity assessment."""
    g = group.copy()
    g['_order'] = pd.to_numeric(g['message_index'], errors='coerce')
    g = g.sort_values('_order', kind='stable')
    if 'message_id' in g:
        ids = g['message_id'].astype(str).str.strip()
        g = g.loc[~(ids.ne('') & ids.duplicated())]
    parts, dialogue = [], []
    for _, record in g.iterrows():
        content = safe_text(record.get('content'))
        if not content: continue
        role = str(record.get('role', '')).strip()
        if role in ('0', '0.0'):
            parts.append(content)
            dialogue.append({'speaker': 'citizen', 'text': content})
        elif role in ('1', '1.0'):
            dialogue.append({'speaker': 'avatar', 'text': content})
    return '\n'.join(parts), len(parts), dialogue

def save_file(df,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.hm.tmp')
    df.to_csv(tmp,index=False,encoding='utf-8-sig')
    try: tmp.replace(path)
    except PermissionError:
        raise PermissionError(f'Cannot replace {path}. Close Excel and CSV previews, or use --no-writeback.') from None

def write_jsonl_atomic(records, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.hm.tmp')
    with tmp.open('w', encoding='utf-8') as fh:
        for item in records:
            fh.write(json.dumps(item, ensure_ascii=False) + '\n')
    try:
        tmp.replace(path)
    except PermissionError:
        raise PermissionError(f'Cannot replace {path}; close any file preview or editor locking it.') from None


def summarize_session(s, rec):
    row = {
        'session_id': s['session_id'],
        'hm_scoring_status': 'no_user_response' if not s['user_text'] else 'pending',
        'hm_user_message_count': s['user_messages'],
        'hm_rubric_version': VERSION,
    }
    if not rec:
        return row
    if (rec.get('text_sha256') != s['text_sha256']
            or rec.get('rubric_version') != VERSION
            or rec.get('model') != s['model']):
        return row
    raw, fin = rec['raw_ai_result'], rec['calculated']
    row.update({
        'hm_scoring_status': 'completed',
        'hm_principal_issue': raw['principal_issue'],
        'hm_topic_code': raw['validated_topic_code'],
        'hm_topic_rationale': raw['topic_rationale'],
        'hm_human_review_required': fin['human_review_required'],
        'hm_human_review_reason': fin['review_reason'],
        'hm_urgency_route': fin['dimensions']['urgency'].get('route'),
        'hm_urgency_rationale': raw['urgency']['rationale'],
        'hm_urgency_confidence': raw['urgency']['confidence'],
        'hm_urgency_critical_gates_json': json.dumps(
            fin['dimensions']['urgency']['critical_gates'], ensure_ascii=False),
    })
    for name in WEIGHTS:
        dim = fin['dimensions'][name]
        prefix = 'hm_' + name
        row[prefix + '_score'] = dim['score']
        row[prefix + '_status'] = dim['status']
        row[prefix + '_coverage'] = dim['coverage']
        row[prefix + '_details_json'] = json.dumps(raw[name], ensure_ascii=False)
        row[prefix + '_calculation_json'] = json.dumps(dim, ensure_ascii=False)
        if name in LEVELS:
            row[prefix + '_level'] = level(dim['score'], LEVELS[name])
    return row


def main():
    ap = argparse.ArgumentParser(description='Home Minister session scoring; incremental, per-dataset outputs')
    ap.add_argument('--input-dir', default='output data')
    ap.add_argument('--batch-size', type=int, default=8, help='progress checkpoint interval (API calls sequential)')
    ap.add_argument('--model', default='gpt-5-nano')
    ap.add_argument('--max-sessions', type=int, default=0, help='maximum NEW API requests this run; 0 means all')
    ap.add_argument('--session-id', action='append', default=[], help='target one session ID; repeat option for multiple')
    ap.add_argument('--session-ids-file', help='optional UTF-8 text file, one session ID per line')
    ap.add_argument('--force', action='store_true', help='rescore selected sessions even if their result is cached')
    ap.add_argument('--dry-run', action='store_true', help='display which sessions need scoring without API requests or writes')
    ap.add_argument('--no-writeback', action='store_true', help='save JSONL and summary, not original cleaned CSV')
    args = ap.parse_args()
    folder = Path(args.input_dir).expanduser()
    if not folder.is_dir():
        ap.error('Folder not found: ' + str(folder.resolve()))
    if args.batch_size < 1 or args.max_sessions < 0:
        ap.error('Batch size must be >=1 and max-sessions >=0')
    ids = set(args.session_id)
    if args.session_ids_file:
        ids.update(x.strip() for x in Path(args.session_ids_file).read_text(encoding='utf-8-sig').splitlines() if x.strip() and not x.lstrip().startswith('#'))
    files = sorted(p for p in folder.rglob('*.csv') if p.name.endswith('[cleaned].csv'))
    print('Cleaned files found:', len(files), flush=True)
    if not files: return
    frames, groups, caches, jsonpaths = {}, {}, {}, {}
    for path in files:
        df = pd.read_csv(path, dtype='string', keep_default_na=False, encoding='utf-8-sig')
        missing = {'session_id', 'message_index', 'role', 'content'} - set(df.columns)
        if missing: raise ValueError(f'{path.name} missing {sorted(missing)}')
        frames[path] = df
        sessions = []
        for sid, g in df.groupby('session_id', sort=False):
            if not safe_text(sid): continue
            user_text, count, dialogue = get_content(g)
            first = g.iloc[0]
            dataset = path.relative_to(folder).as_posix()
            sessions.append({
                'key': hashlib.sha256((dataset + '|' + str(sid)).encode()).hexdigest(),
                'dataset': dataset, 'session_id': str(sid), 'user_text': user_text,
                'text_sha256': hashlib.sha256(json.dumps(dialogue, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                'dialogue': dialogue,
                'model': args.model, 'user_messages': count,
                'language': safe_text(first.get('language_name', first.get('language_code', ''))),
                'upstream_topic': safe_text(first.get('ministry_topic_code', '')),
                'upstream_intent': safe_text(first.get('intent', '')),
            })
        groups[path] = sessions
        audit_path = path.with_name(path.stem + '_home_minister_scoring.jsonl')
        jsonpaths[path] = audit_path
        cache = {}
        if audit_path.exists():
            for line in audit_path.read_text(encoding='utf-8-sig').splitlines():
                if not line.strip(): continue
                try:
                    rec = json.loads(line)
                    if rec.get('key'): cache[rec['key']] = rec
                except (ValueError, TypeError):
                    print('WARNING: skipped malformed audit line in', audit_path.name)
        caches[path] = cache
        print(f'{path.name}: {len(df):,} rows, {len(sessions):,} unique sessions, {len(cache):,} cached', flush=True)

    if ids:
        found = {s['session_id'] for sessions in groups.values() for s in sessions if s['session_id'] in ids}
        missing_ids = ids - found
        if missing_ids: print('WARNING: requested session IDs not found:', ', '.join(sorted(missing_ids)))

    pending = []
    for path, sessions in groups.items():
        cache = caches[path]
        for s in sessions:
            if not s['user_text'] or (ids and s['session_id'] not in ids): continue
            old = cache.get(s['key'])
            valid = (old is not None and old.get('text_sha256') == s['text_sha256']
                     and old.get('rubric_version') == VERSION and old.get('model') == args.model)
            if args.force or not valid:
                pending.append((path, s))
    print(f'API scoring needed: {len(pending):,} sessions. Others are cached or have no user response.', flush=True)
    if args.dry_run:
        for path, s in pending[:30]: print('  NEEDS SCORING:', path.name, s['session_id'])
        if len(pending) > 30: print(f'  ... and {len(pending) - 30} more')
        return
    if pending and not os.getenv('OPENAI_API_KEY'):
        raise RuntimeError('OPENAI_API_KEY is missing. Set it in your Jupyter environment; never paste the key into this .py file.')
    client = OpenAI(timeout=120, max_retries=2) if pending else None
    limit = args.max_sessions or len(pending)
    succeeded = failed = 0
    for n, (path, s) in enumerate(pending[:limit], start=1):
        print(f'[{n}/{min(limit,len(pending))}] {path.name} / {s["session_id"]}', flush=True)
        try:
            response = client.responses.parse(
                model=args.model, instructions=INSTRUCTIONS,
                input=json.dumps({
                    'session_id': s['session_id'], 'language': s['language'],
                    'upstream_topic_context': s['upstream_topic'],
                    'upstream_intent_context': s['upstream_intent'],
                    'conversation_in_order': s['dialogue'],
                    'evidence_rule': 'Only citizen utterances may be quoted as evidence; avatar prompts are context only.'}, ensure_ascii=False),
                text_format=RawSession,
            )
            raw = response.output_parsed
            if raw is None: raise RuntimeError('No parsed output returned')
            rec = {'key': s['key'], 'dataset': s['dataset'], 'session_id': s['session_id'],
                   'text_sha256': s['text_sha256'], 'rubric_version': VERSION,
                   'model': args.model, 'raw_ai_result': raw.model_dump(), 'calculated': finish(raw)}
            caches[path][s['key']] = rec
            # Persist each scored session immediately. Safe to restart after interruption.
            with jsonpaths[path].open('a', encoding='utf-8') as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
            succeeded += 1
        except Exception as ex:
            failed += 1
            print('  ERROR:', type(ex).__name__, str(ex)[:350], flush=True)
        if n % args.batch_size == 0:
            print('Checkpoint: success', succeeded, 'failed', failed, flush=True)

    # Recreate one summary beside EACH cleaned CSV and append matching HM columns to it.
    # Includes cached records for previously completed sessions and keeps all original rows.
    for path, sessions in groups.items():
        result = pd.DataFrame([summarize_session(s, caches[path].get(s['key'])) for s in sessions])
        summary_path = path.with_name(path.stem + '_home_minister_session_summary.csv')
        save_file(result, summary_path)
        print('Saved summary:', summary_path, flush=True)
        # Compact audit log to latest version per session, avoiding duplicates after forced rescoring.
        # Old content hashes are retained only when current; no JSON records fabricated for unscored sessions.
        records = [caches[path][s['key']] for s in sessions
                   if s['key'] in caches[path]]
        write_jsonl_atomic(records, jsonpaths[path])
        print('Saved JSONL:', jsonpaths[path], 'records:', len(records), flush=True)
        if args.no_writeback: continue
        df = frames[path]
        oldcols = [c for c in df.columns if not c.startswith('hm_')]
        result_cols = [c for c in result.columns if c != 'session_id']
        clean = df.drop(columns=[c for c in df.columns if c.startswith('hm_')], errors='ignore')
        merged = clean.merge(result[['session_id'] + result_cols], on='session_id', how='left',
                             validate='many_to_one', sort=False)
        if len(merged) != len(df): raise AssertionError('Row count changed! Refusing to overwrite.')
        for c in oldcols:
            if not merged[c].astype('string').fillna('').reset_index(drop=True).equals(
                    clean[c].astype('string').fillna('').reset_index(drop=True)):
                raise AssertionError(f'Original column changed: {c}')
        save_file(merged, path)
        print('Updated cleaned CSV:', path, '+', len(result_cols), 'HM columns', flush=True)
    print(f'FINISHED. New scores: {succeeded}, API errors: {failed}. Non-HM columns preserved.', flush=True)


if __name__ == '__main__':
    main()
