# weather-stub-server

A tiny **CPU-only** FastAPI service that mimics the scoring contracts of
Microsoft Aurora and NVIDIA Earth-2 FCN. Lets the Planetary Explorer
Forecast Agent be built, tested, and demoed end-to-end without GPU quota.

## Endpoints

| Method | Path                 | Mimics                          |
|--------|----------------------|---------------------------------|
| GET    | `/health`            | liveness                        |
| GET    | `/info`              | model card                      |
| POST   | `/aurora/score`      | Microsoft Aurora 1.x            |
| POST   | `/earth2/fcn/score`  | NVIDIA Earth-2 FourCastNet v2   |

### Request

```json
{
  "lat": 38.9,
  "lon": -77.0,
  "lead_hours": 72,
  "variables": ["t2m", "precip", "u10", "v10"],
  "grid_size": 8
}
```

### Response (FCN)

```json
{
  "model": "earth2-fcn",
  "issued_at": "2026-05-27T12:00:00Z",
  "valid_at":  "2026-05-30T12:00:00Z",
  "lead_hours": 72,
  "grid": { "lat": [...], "lon": [...] },
  "variables": { "t2m": [[...]], "precip": [[...]] },
  "units": { "t2m": "K", "precip": "mm/hr" },
  "stub": true
}
```

Aurora additionally returns `cyclone_tracks` when `"cyclone"` is included
in `variables`.

## Auth

If env `STUB_API_KEY` is set, requests must send
`Authorization: Bearer <STUB_API_KEY>`. Unset = open (local dev only).

## Run locally

```pwsh
pip install -r requirements.txt
uvicorn app:app --reload --port 8080
```

## Run in Docker

```pwsh
docker build -t weather-stub .
docker run -p 8080:8080 -e STUB_API_KEY=dev weather-stub
```

## Swap to a real GPU endpoint

When A100 quota lands, deploy the real Aurora / Earth-2 NIM endpoints
and point the Forecast Agent's `AURORA_ENDPOINT_URL` and
`EARTH2_FCN_ENDPOINT_URL` env vars at them. The request/response shape
is the same — no agent code changes.
