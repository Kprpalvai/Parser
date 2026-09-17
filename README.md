# Job Application Tracker — Public Web Deployment

A full-stack browser dashboard for tracking job applications, apply/portal links, resume-vs-job-description ATS alignment, role-specific resume changes, hiring-manager/referral notes, and reporting.

## Run locally

Requires Python 3.10+.

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Open `http://127.0.0.1:8000`.

## Deploy to Railway and get a public HTTPS link

This package is deployment-ready for Railway. Railway can build the included Dockerfile and expose the FastAPI app on a public domain.

Recommended production settings:

1. Create a Railway project and deploy this folder/repository.
2. Add a persistent Volume and mount it at `/data`.
3. Add environment variable `DB_PATH=/data/tracker.db`.
4. Generate a public domain for the service. Railway will provide an HTTPS URL.
5. Verify `https://YOUR-DOMAIN/health` returns `{"status":"ok"}`.

The included `railway.toml` configures `/health` as the deployment health check. Railway supplies the `PORT` environment variable automatically.

## Important privacy note

The current MVP does not include user accounts. If you publish the URL openly, anyone who can reach it can view or edit the same application data. For a personal dashboard, keep the URL private until authentication is added. For a true multi-user public product, add authentication and per-user data isolation before inviting users.

## ATS scoring note

The ATS score is a transparent keyword-alignment heuristic, not an official score from any ATS vendor. It is designed to help prioritize tailoring while keeping the resume truthful and readable.

## Production roadmap

Recommended next upgrades: user authentication, PostgreSQL with per-user ownership, encrypted resume storage, PDF/DOCX parsing, email/calendar integrations, live job ingestion, licensed contact enrichment, and AI-assisted resume rewrites that require user approval.
