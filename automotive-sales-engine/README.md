# Automotive Sales Engine — Tahoe Lead Capture

First live lead-capture slice for the vehicle-centered sales engine.

## Vehicle
- 2018 Chevrolet Tahoe LS
- VIN: 1GNSCAKC2JR270624
- Stock: JR270624
- Mileage: 137,069
- Advertised price: $17,590*

## Flow
Ad click → vehicle landing page → form submission → customer + exact VIN attribution → opportunity NEW → FIRST_CONTACT → LEAD_CAPTURED engine event.

## Local run
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:ADMIN_TOKEN="replace-with-a-long-random-secret"
.\.venv\Scripts\python.exe -m uvicorn app:app --reload
```

Open:
`http://127.0.0.1:8000/v/JR270624?utm_source=facebook&utm_medium=paid_social&utm_campaign=tahoe01&utm_content=value01`

## Railway deployment
Deploy this folder as the service root.

Environment:
- `ADMIN_TOKEN` = long random secret
- `LEADS_DB_PATH=/data/leads.db`

Attach a persistent volume mounted at `/data`.

Health check:
`/health`

First Facebook campaign URL:
`/v/JR270624?utm_source=facebook&utm_medium=paid_social&utm_campaign=tahoe01&utm_content=value01`

## Important
Replace the placeholder media with the actual Tahoe photo/video frame before paid traffic.
