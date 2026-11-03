"""Local FastAPI orchestration layer for the DengarAI CSV -> HTML pipeline."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from fastapi.openapi.utils import get_openapi

ROOT = Path(__file__).resolve().parent
WORK = ROOT / 'data' / 'jobs'
SCRIPTS = ROOT / 'scripts'
STAGES = ('cleaning', 'sentiment_topic', 'ai_scoring', 'analysis', 'dashboard')
MAX_UPLOAD_BYTES = 250 * 1024 * 1024  # limit per file, local demo

app = FastAPI(title='DengarAI Processing API', version='1.0.0',
              description='Runs five existing Python stages sequentially. Local development only.')
@app.get("/")
def home():
    return {
        "service": "DengarAI FastAPI",
        "status": "online",
        "documentation": "/docs",
        "health": "/health"
    }
jobs: dict[str, dict] = {}
lock = threading.Lock()


class StartOptions(BaseModel):
    sentiment_batch_size: int = Field(default=8, ge=1, le=128)
    scoring_batch_size: int = Field(default=8, ge=1, le=128)
    scoring_model: str = Field(default='gpt-5-nano', min_length=1)
    max_new_scoring_sessions: int = Field(default=0, ge=0,
        description='0 = all eligible uncached sessions; a positive value limits new scoring calls.')
    force_rescore: bool = False
    include_dashboard: bool = True


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_job(job_id: str) -> dict:
    with lock:
        item = jobs.get(job_id)
        if item is None:
            raise HTTPException(404, 'Unknown job ID (jobs are kept in memory until server restart)')
        return dict(item)


def update(job_id: str, **changes):
    with lock:
        jobs[job_id].update(changes, updated_at=stamp())
        snapshot = dict(jobs[job_id])
    folder = WORK / job_id
    # Metadata updated atomically after each stage. No API keys are written.
    tmp = folder / 'status.tmp'
    tmp.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
    tmp.replace(folder / 'status.json')


def run_command(job_id: str, stage: str, cmd: list[str], log_file: Path) -> None:
    update(job_id, stage=stage, state='running')
    with log_file.open('a', encoding='utf-8') as log:
        log.write(f'\n[{stamp()}] STAGE {stage}\nCOMMAND: {cmd[0]} {Path(cmd[1]).name} ...\n')
        log.flush()
        result = subprocess.run(cmd, cwd=str(ROOT), stdout=log,
                                stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f'{stage} failed (exit code {result.returncode}); see log endpoint')


def scoring_json_exports(processed: Path) -> int:
    """Convert each scored JSONL into a conventional JSON array beside it."""
    converted = 0
    for path in processed.rglob('*_home_minister_scoring.jsonl'):
        records = []
        with path.open('r', encoding='utf-8-sig') as f:
            for line_number, line in enumerate(f, 1):
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        raise RuntimeError(f'Malformed scoring JSONL at {path}:{line_number}') from e
        target = path.with_suffix('.json')
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(target)
        converted += 1
    return converted


def execute_pipeline(job_id: str, opts: StartOptions) -> None:
    root = WORK / job_id
    raw = root / 'raw'
    processed = root / 'processed'
    html = root / 'html'
    processed.mkdir(exist_ok=True)
    html.mkdir(exist_ok=True)
    log_file = root / 'pipeline.log'
    try:
        run_command(job_id, 'cleaning', [sys.executable, str(SCRIPTS / 'data_cleaning.py'),
                 '--input-dir', str(raw), '--output-dir', str(processed)], log_file)
        cleaned = [p for p in processed.rglob('*.csv') if p.name.endswith('[cleaned].csv')]
        if not cleaned:
            raise RuntimeError('Cleaning produced no [cleaned].csv datasets')
        run_command(job_id, 'sentiment_topic', [sys.executable, str(SCRIPTS / 'sentiment_topic.py'),
                    '--input-dir', str(processed), '--batch-size', str(opts.sentiment_batch_size)], log_file)
        score_cmd = [sys.executable, str(SCRIPTS / 'ai_scoring.py'),
                     '--input-dir', str(processed), '--batch-size', str(opts.scoring_batch_size),
                     '--model', opts.scoring_model, '--max-sessions', str(opts.max_new_scoring_sessions)]
        if opts.force_rescore:
            score_cmd.append('--force')
        run_command(job_id, 'ai_scoring', score_cmd, log_file)
        scoring_json_exports(processed)
        run_command(job_id, 'analysis', [sys.executable, str(SCRIPTS / 'analyzation.py'),
                    '--input-dir', str(processed), '--output', str(processed / 'analyzed.csv')], log_file)
        if opts.include_dashboard:
            required = ['executive_v9.py', 'operations_v9.py', 'user_behavior_v9.py',
                        'citizen_voice_v9.py', 'citizen_issue_intelligence_v9.py']
            missing = [name for name in required if not (SCRIPTS / name).is_file()]
            if missing:
                update(job_id, stage='dashboard', state='partial',
                       detail='Analysis completed. Dashboard dependencies missing: ' + ', '.join(missing),
                       analyzed_csv_ready=True)
                return
            run_command(job_id, 'dashboard', [sys.executable, str(SCRIPTS / 'dashboard_v9.py'),
                        '--input', str(processed / 'analyzed.csv'), '--output', str(html / 'dashboard_v9.html'),
                        '--no-open'], log_file)
        update(job_id, stage='complete', state='completed', analyzed_csv_ready=True,
               detail='Pipeline finished successfully')
    except Exception as exc:
        update(job_id, state='failed', detail=str(exc),
               analyzed_csv_ready=(processed / 'analyzed.csv').is_file())


@app.get('/health')
def health():
    return {'status': 'ok', 'stages': STAGES}


@app.post('/api/jobs/upload', status_code=201)
def upload_raw_datasets(files: list[UploadFile] = File(..., description="Upload two or more CSV files")):
    if len(files) < 2:
        raise HTTPException(422, 'Upload at least two raw CSV files')
    names = [f.filename for f in files]
    if any(not n or not n.lower().endswith('.csv') for n in names):
        raise HTTPException(422, 'Every file must be a CSV')
    if len({n.lower() for n in names}) != len(names):
        raise HTTPException(422, 'CSV filenames must be unique (case-insensitive)')
    job_id = uuid.uuid4().hex
    raw = WORK / job_id / 'raw'
    raw.mkdir(parents=True)
    try:
        for uploaded in files:
            # Ignore supplied directories; prevent traversal and encoded separators.
            name = Path(uploaded.filename.replace('\\', '/')).name
            if not re.fullmatch(r'[A-Za-z0-9 _().\[\]-]+\.csv', name, re.IGNORECASE):
                raise HTTPException(422, f'Unsupported filename: {uploaded.filename}')
            total = 0
            with (raw / name).open('wb') as out:
                while True:
                    chunk = uploaded.file.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, f'{name} exceeds 250 MB')
                    out.write(chunk)
    except Exception:
        shutil.rmtree(WORK / job_id, ignore_errors=True)
        raise
    finally:
        for uploaded in files:
            uploaded.file.close()
    with lock:
        jobs[job_id] = {'job_id': job_id, 'state': 'uploaded', 'stage': None,
                        'datasets': names, 'created_at': stamp(), 'detail': '',
                        'analyzed_csv_ready': False}
    update(job_id)
    return get_job(job_id)


@app.post('/api/jobs/{job_id}/run', status_code=202)
def run_job(job_id: str, options: StartOptions):
    with lock:
        if job_id not in jobs:
            raise HTTPException(404, 'Unknown job')
        if jobs[job_id]['state'] != 'uploaded':
            raise HTTPException(409, 'Job must be in uploaded state; use a new job for a new run')
        jobs[job_id]['state'] = 'queued'
    update(job_id, detail='Queued for sequential processing')
    worker = threading.Thread(target=execute_pipeline, args=(job_id, options), daemon=True)
    worker.start()
    return get_job(job_id)


@app.get('/api/jobs/{job_id}')
def status(job_id: str):
    return get_job(job_id)


@app.get('/api/jobs/{job_id}/log')
def log(job_id: str):
    get_job(job_id)
    path = WORK / job_id / 'pipeline.log'
    if not path.is_file():
        return {'log': 'No processing log yet'}
    return {'log': path.read_text(encoding='utf-8', errors='replace')[-30000:]}


@app.get('/api/jobs/{job_id}/files')
def list_files(job_id: str):
    get_job(job_id)
    folder = WORK / job_id
    return {'files': [p.relative_to(folder).as_posix() for p in folder.rglob('*')
                      if p.is_file() and p.name != 'status.tmp']}


@app.get('/api/jobs/{job_id}/files/{file_path:path}')
def download(job_id: str, file_path: str):
    get_job(job_id)
    root = (WORK / job_id).resolve()
    requested = (root / file_path).resolve()
    if not requested.is_relative_to(root) or not requested.is_file():
        raise HTTPException(404, 'File not found')
    if requested.suffix.lower() not in {'.csv', '.json', '.jsonl', '.html'}:
        raise HTTPException(403, 'File type not downloadable')
    return FileResponse(requested)


@app.get('/api/jobs/{job_id}/dashboard')
def dashboard(job_id: str):
    return download(job_id, 'html/dashboard_v9.html')


# Fix Swagger file upload display
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    upload_schema = schema["components"]["schemas"][
        "Body_upload_raw_datasets_api_jobs_upload_post"
    ]

    file_schema = upload_schema["properties"]["files"]["items"]
    file_schema["format"] = "binary"
    file_schema.pop("contentMediaType", None)

    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi
