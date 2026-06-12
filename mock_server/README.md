# Mock Backend Service for Payment Exception Resolution System

This is a mock backend service built with FastAPI that simulates upstream banking systems and serves data to downstream agents.

## Getting Started

1. Create a virtual environment and install dependencies:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

2. Generate the mock data:
```bash
python generate_data.py
```

3. Run the server:
```bash
uvicorn app:app --reload
```

4. Open the Swagger UI in your browser:
http://127.0.0.1:8000/docs

## Orchestrator-compatible endpoints

The raw `/exceptions`, `/payments`, and `/compliance` resources are upstream-style mock records. The orchestrator expects the canonical `CanonicalPaymentException` shape instead, so use these adapter endpoints for orchestrator integration:

- `GET /exceptions/{case_id}/canonical`: returns one canonical payment exception payload for a case.
- `GET /exceptions/random/canonical`: returns a random canonical payment exception payload.

The adapter joins exception, payment, and compliance records, fills MVP policy/default evidence fields, and makes the exception scenario authoritative for routing. In particular, only `COMPLIANCE_HOLD` emits a live `compliance_hold_status`; other exception types normalize it to `NONE` so generated mock noise does not force `ComplianceAgent` routing.
