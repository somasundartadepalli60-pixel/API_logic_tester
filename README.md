# APIPath Sentinel — API Authorization Logic Tester

APIPath Sentinel is a local-first web tool for checking whether API endpoints enforce expected role-based authorization consistently. It imports OpenAPI specifications, lets a tester define expected Allow/Deny rules per role, sends individual test requests using explicitly supplied test-account headers, compares the observed result with the expected decision, and stores reproducible evidence in SQLite.

## What it does

- Import OpenAPI 3.x / Swagger-style JSON or YAML specifications with `paths`.
- Discover endpoint operations and inspect their parameters and request-body definitions.
- Define an expected `Allow` or `Deny` result for each endpoint and role.
- Run one controlled request at a time against a base URL you provide.
- Supply test-account headers, path values, query parameters, and JSON body.
- Compare response decisions: 2xx/3xx = allow, 401/403 = deny; other statuses are inconclusive.
- Save test results, timing, redacted request headers, response status/headers/body excerpt, and downloadable JSON evidence.
- View run history and a simple report dashboard.
- Store specs, rules, and evidence locally in SQLite.

## Important testing boundary

Only test APIs you own or have explicit permission to assess. Use dedicated test accounts and non-production data. This app does not crawl an API or automatically enumerate user IDs. It sends only the single request you explicitly configure for the selected endpoint. Avoid destructive operations against production. A 2xx response does not prove that the returned data belongs to the right user; inspect evidence and test with controlled records.

## Run locally

Requires Python 3.10+.

### Windows PowerShell

```powershell
cd APIPath_Sentinel
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

### macOS / Linux

```bash
cd APIPath_Sentinel
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in your browser. The database file `apipath_sentinel.db` is created automatically on first run. No external API keys or cloud services are required for the tool itself. The bundled GitHub starter can query public GitHub API data without a token; authenticated/private-resource checks require credentials you supply for an account you control.

## Quick start — real live API starter

1. Start the app and open `http://127.0.0.1:5000`.
2. On the dashboard, click **Load GitHub API starter** to import a curated subset of the official GitHub REST API documentation. The app does not mock these API responses: requests go to `https://api.github.com`.
3. Open a read-only `GET` endpoint, add an expected rule for a role such as `public-reader`, and save it.
4. In **Run a test**, set the base URL to `https://api.github.com`, choose the role, fill in the path values below, and check the authorization confirmation.
5. Inspect the actual response status, body excerpt, timing, and saved evidence.

Starter values:

- `GET /users/{username}` — path values: `{"username":"octocat"}`
- `GET /repos/{owner}/{repo}` — path values: `{"owner":"octocat","repo":"Spoon-Knife"}`
- `GET /repos/{owner}/{repo}/issues` — path values: `{"owner":"octocat","repo":"Spoon-Knife"}`; query: `{"state":"open","per_page":2}`
- `GET /rate_limit` — no path values needed.

Official documentation: https://docs.github.com/en/rest. GitHub's unauthenticated API is rate-limited (currently documented as 60 requests/hour); keep testing low-volume and stop if you receive rate-limit responses. See https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api.

These public GET endpoints demonstrate real live API requests, but **they do not prove broken object-level authorization** because public profile/repository data is intended to be publicly accessible. To test authorization flaws meaningfully, import the OpenAPI specification for an API you own or are explicitly authorized to test and use dedicated test accounts with different roles. Never use another person's credentials or attempt to access private resources without permission.

For any other authorized API, the original workflow remains: prepare an OpenAPI `.json`, `.yaml`, or `.yml` file and import it from the dashboard.
3. Open an endpoint.
4. Add a role such as `owner`, `member`, or `admin`, and choose the expected access decision.
5. In **Run a controlled test**, enter your local/staging API base URL, role, path parameter values, and test-account headers as JSON.
6. If the operation needs a body or query parameters, provide valid JSON.
7. Check the result and open the evidence JSON for a reproducible record.

Example headers:

```json
{
  "Authorization": "Bearer REPLACE_WITH_TEST_ACCOUNT_TOKEN"
}
```

Example path values for `/users/{userId}`:

```json
{
  "userId": "test-user-123"
}
```

Example request body:

```json
{
  "displayName": "Authorization test"
}
```

## Understanding outcomes

- **PASS** — observed allow/deny decision matches the saved expectation.
- **FAIL** — observed allow/deny decision differs from the saved expectation. Review the evidence carefully; a mismatch is a signal to investigate, not by itself a confirmed vulnerability.
- **INCONCLUSIVE** — network error or an HTTP response outside the simple classification rules, such as 404, 429, or 500. These need manual review.
- `2xx` and `3xx` are classified as allow; `401` and `403` are classified as deny. A redirect is not followed. Application-specific semantics may require changing this interpretation.

## Data and privacy

All state is stored locally in `apipath_sentinel.db`. Uploaded OpenAPI specs are stored as parsed JSON in that database. Evidence retains response excerpts (up to 1,500 characters), so do not test with sensitive production data. Authorization, Cookie, and X-API-Key request header values are redacted in stored evidence, but avoid placing secrets in request bodies or query parameters. Delete the database file to clear all local data after stopping the app.

## Current scope / known limitations

- No automatic login flow, OAuth refresh, token vault, or secrets manager.
- No automatic resource-ID discovery or cross-user fuzzing; provide controlled test values yourself.
- OpenAPI `$ref` objects are retained but not fully dereferenced in the UI.
- The first version uses simple status-code-based allow/deny classification; it does not infer business-level authorization from response contents.
- No multi-user login or deployment hardening; intended for local developer/QA use.
- Do not expose the development server to the public internet.

## Project structure

```text
APIPath_Sentinel/
├── app.py
├── requirements.txt
├── README.md
├── LICENSE
├── .gitignore
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── spec_detail.html
│   ├── endpoint_detail.html
│   ├── run_detail.html
│   └── reports.html
└── static/
    └── style.css
```

## Troubleshooting

- **`ModuleNotFoundError`**: activate the virtual environment and run `pip install -r requirements.txt`.
- **YAML parse error**: confirm indentation and that the file is valid YAML.
- **No operations found**: check that the specification has HTTP methods nested beneath `paths`.
- **Connection refused**: confirm your local/staging API is running and the base URL and port are correct.
- **Unexpected INCONCLUSIVE**: inspect the response status and application logs; 404/429/5xx are intentionally not automatically treated as allow or deny.



## Generated offline API contract corpus
This project contains 510,000 **generated data-case lines** in 100 Python fixture modules. These are structured test vectors, not 510,000 independently authored lines of application logic. They exercise validation of HTTP methods, paths, status codes, roles and policy expectations.

Run one pack: `python -m casepacks --pack 1`

Run unit tests: `python -m unittest discover -s tests`

Run Flask UI: `python app.py` (install requirements first).

## Git and simulated PRs
Git history includes feature-branch merges for 80 local PR-style workflows. `LOCAL_PR_SIMULATIONS.json` describes them. These are **not hosted GitHub/GitLab pull requests**, and must not be represented as such.


## Reproducible local commands and dependency metadata

The Python application uses `requirements.txt` and `pyproject.toml` for its Python dependencies.
`requirements.lock` lists *direct constraints only* and is not a fully resolved Python lock.
`package-lock.json` is an npm-generated lock for the **dependency-free command launcher**
(`package.json`), not for Flask or other Python packages.

```bash
npm ci
npm run build
npm test
npm start
```

Alternatively use `python -m pip install -r requirements.txt` and `python app.py`.
The npm scripts require Python on your PATH. No API keys or `.env` file are needed.

## Collaboration and PR provenance

`LOCAL_PR_SIMULATIONS.json` and `LOCAL_PR_ADDITIONS.json` describe locally merged
feature branches. They are **not hosted pull requests**, and the commit author
is one local project identity, not evidence of multiple independent contributors.
For the hosted-PR and distinct-collaborator checks, publish this repository,
invite a real collaborator, and have contributors open and merge genuine PRs.
