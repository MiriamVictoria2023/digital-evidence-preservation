from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, uuid
from db import connect, init_db

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / 'storage' / 'evidence'
LOG_DIR = ROOT / 'logs'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5173"]}})
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
init_db()


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def custody_hash(evidence_id, action, actor, notes, event_time, previous_hash):
    payload = '|'.join(map(str, [evidence_id, action, actor, notes, event_time, previous_hash]))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def add_custody(db, evidence_id, action, actor, notes=''):
    last = db.execute('SELECT entry_hash FROM custody ORDER BY id DESC LIMIT 1').fetchone()
    previous = last['entry_hash'] if last else 'GENESIS'
    event_time = now()
    entry_hash = custody_hash(evidence_id, action, actor, notes, event_time, previous)
    db.execute('INSERT INTO custody (evidence_id,action,actor,notes,event_time,previous_hash,entry_hash) VALUES (?,?,?,?,?,?,?)',
               (evidence_id, action, actor, notes, event_time, previous, entry_hash))
    db.execute('INSERT INTO audit_log (event,actor,details,event_time) VALUES (?,?,?,?)',
               (action, actor, f'evidence_id={evidence_id}; {notes}', event_time))
    with open(LOG_DIR / 'evidence_log.txt', 'a', encoding='utf-8') as log:
        log.write(json.dumps({'evidence_id': evidence_id, 'action': action, 'actor': actor,
                              'event_time': event_time, 'previous_hash': previous,
                              'entry_hash': entry_hash}) + '\n')


@app.get('/api/health')
def health():
    return jsonify({'status': 'ok', 'service': 'Digital Evidence Preservation API'})


@app.post('/api/evidence')
def upload_evidence():
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'A file is required'}), 400
    case_ref = request.form.get('case_ref', '').strip()
    title = request.form.get('title', '').strip()
    actor = request.form.get('uploaded_by', '').strip()
    if not case_ref or not title or not actor:
        return jsonify({'error': 'case_ref, title and uploaded_by are required'}), 400
    original = secure_filename(file.filename)
    stored = f'{uuid.uuid4().hex}_{original}'
    path = UPLOAD_DIR / stored
    file.save(path)
    digest = sha256_file(path)
    collected_at = request.form.get('collected_at') or now()
    with connect() as db:
        cur = db.execute('''INSERT INTO evidence (case_ref,title,description,original_filename,stored_filename,sha256,size_bytes,uploaded_by,collected_at,created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?)''',
                         (case_ref, title, request.form.get('description',''), original, stored, digest,
                          path.stat().st_size, actor, collected_at, now()))
        evidence_id = cur.lastrowid
        add_custody(db, evidence_id, 'EVIDENCE_REGISTERED', actor, f'SHA-256={digest}')
        row = db.execute('SELECT * FROM evidence WHERE id=?', (evidence_id,)).fetchone()
    return jsonify(dict(row)), 201


@app.get('/api/evidence')
def list_evidence():
    with connect() as db:
        rows = db.execute('SELECT * FROM evidence ORDER BY id DESC').fetchall()
    return jsonify([dict(r) for r in rows])


@app.get('/api/evidence/<int:evidence_id>')
def get_evidence(evidence_id):
    with connect() as db:
        row = db.execute('SELECT * FROM evidence WHERE id=?', (evidence_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Evidence not found'}), 404
        custody = db.execute('SELECT * FROM custody WHERE evidence_id=? ORDER BY id', (evidence_id,)).fetchall()
    return jsonify({'evidence': dict(row), 'custody': [dict(x) for x in custody]})


@app.post('/api/evidence/<int:evidence_id>/verify')
def verify_evidence(evidence_id):
    actor = (request.json or {}).get('actor', 'system')
    with connect() as db:
        row = db.execute('SELECT * FROM evidence WHERE id=?', (evidence_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Evidence not found'}), 404
        path = UPLOAD_DIR / row['stored_filename']
        exists = path.is_file()
        current = sha256_file(path) if exists else None
        valid = exists and current == row['sha256']
        add_custody(db, evidence_id, 'INTEGRITY_VERIFIED' if valid else 'INTEGRITY_CHECK_FAILED', actor,
                    f'stored_hash={row["sha256"]}; current_hash={current}')
    return jsonify({'evidence_id': evidence_id, 'file_exists': exists, 'integrity_valid': valid,
                    'stored_sha256': row['sha256'], 'current_sha256': current})


@app.get('/api/evidence/<int:evidence_id>/download')
def download_evidence(evidence_id):
    actor = request.args.get('actor', 'system')
    with connect() as db:
        row = db.execute('SELECT * FROM evidence WHERE id=?', (evidence_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Evidence not found'}), 404
        path = UPLOAD_DIR / row['stored_filename']
        if not path.is_file():
            return jsonify({'error': 'Stored evidence file is missing'}), 404
        add_custody(db, evidence_id, 'EVIDENCE_DOWNLOADED', actor, 'Download requested')
    return send_file(path, as_attachment=True, download_name=row['original_filename'])


@app.get('/api/audit')
def audit():
    with connect() as db:
        rows = db.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT 500').fetchall()
    return jsonify([dict(r) for r in rows])


@app.get('/api/custody/verify')
def verify_custody_chain():
    with connect() as db:
        rows = db.execute('SELECT * FROM custody ORDER BY id').fetchall()
    expected_previous = 'GENESIS'
    failures = []
    for row in rows:
        calculated = custody_hash(row['evidence_id'], row['action'], row['actor'], row['notes'], row['event_time'], row['previous_hash'])
        if row['previous_hash'] != expected_previous or row['entry_hash'] != calculated:
            failures.append(row['id'])
        expected_previous = row['entry_hash']
    return jsonify({'valid': not failures, 'entries_checked': len(rows), 'invalid_entry_ids': failures})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
