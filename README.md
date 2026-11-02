# Digital Evidence Preservation System for Dark Web Investigations

Academic demonstration project for registering, storing, hashing and auditing digital evidence. It is designed for lawful, authorized forensic work; it does not access or crawl dark-web services.

## Objectives
- Register evidence against an investigation/case reference.
- Preserve uploaded files in local storage and record their SHA-256 digest.
- Record custody events with timestamps, actors and linked entry hashes.
- Recalculate file hashes to detect changes after registration.
- Verify the integrity of the custody-event hash chain.
- Provide an investigator-facing React dashboard.

## Architecture
- React + Vite frontend: `frontend/` (development port 5173).
- Python Flask REST API: `backend/app.py` (port 5000).
- SQLite database: created at `backend/evidence.db` on first run.
- Evidence files: `storage/evidence/`.
- Append-only-style JSONL activity export: `logs/evidence_log.txt`.
- Optional Node.js health bridge: `node-bridge/server.js` (port 5001).

## Run locally

### 1. Start Flask API
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

### 2. Start React frontend (new terminal)
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173.

### 3. Optional Node bridge
```bash
cd node-bridge
node server.js
```

## API endpoints
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | API health |
| POST | `/api/evidence` | Upload/register evidence (multipart form) |
| GET | `/api/evidence` | List evidence |
| GET | `/api/evidence/<id>` | Evidence and custody history |
| POST | `/api/evidence/<id>/verify` | Recompute SHA-256 |
| GET | `/api/evidence/<id>/download` | Download evidence and log action |
| GET | `/api/audit` | Recent audit events |
| GET | `/api/custody/verify` | Verify custody hash chain |

## Integrity model
SHA-256 is computed over the uploaded file bytes. Each custody record hashes its evidence ID, action, actor, notes, timestamp and previous entry hash. This provides tamper-evident linkage, but it is not a true immutable ledger: a privileged attacker who can rewrite the database and recompute all hashes could alter the chain. For stronger evidentiary assurance, export signed logs to independently controlled, write-once storage and use trusted timestamping.

## Important limitations and security notes
This is a learning prototype, not a court-certified forensic platform. Before real deployment, add authentication, role-based authorization, CSRF protections, strict upload allowlists, malware scanning in an isolated environment, encryption at rest, secure secrets management, backups, independent timestamping, digital signatures, immutable/WORM audit storage, retention controls, and formal validation. Do not upload unlawful, classified, or sensitive evidence to an unapproved system. Preserve original media and document acquisition methods, tools, operator, time source and hash values.

## Suggested academic evaluation
1. Upload a benign test file and record its SHA-256.
2. Verify it without modifying the file; expect `integrity_valid: true`.
3. In a controlled test copy, modify the stored file and verify again; expect `false`.
4. Register several test events and call `/api/custody/verify`.
5. Document test environment, test cases, observed results and limitations. Do not claim test results until actually executed.
