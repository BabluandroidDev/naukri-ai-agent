# Naukri AI Agent

A local, safety-first AI job-application assistant for Naukri.

This project uses a visible Playwright Chromium browser, a local persistent browser profile, a CSV tracker, and the OpenAI Python SDK to score jobs against your profile. It starts in dry-run mode by default and only final-submits applications when you explicitly enable auto-submit.

## Safety principles

- **No CAPTCHA bypass.** If CAPTCHA, verification, robot-check, or unusual security text is detected, the job is skipped or marked for manual review.
- **No stealth or anti-detection tricks.** The browser is visible by default and uses normal Playwright behavior.
- **No password storage.** You log in manually. The project stores only the local browser session in `data/browser-profile`.
- **Dry-run first.** `dry_run: true` is the default in `config.yaml`.
- **Auto-submit disabled by default.** Final submission requires `--auto-submit` or `auto_submit: true` in `config.yaml`.
- **Skip risky flows.** External company forms, unknown questions, tests, upload requests, suspicious flows, or CAPTCHA are skipped safely.
- **Everything is logged.** Every processed job is written to `data/applications.csv`.

## Folder structure

```text
naukri-ai-agent/
  README.md
  requirements.txt
  .env.example
  config.yaml
  profile.example.json
  answers.example.json
  run.sh
  run.bat
  naukri_agent/
    __init__.py
    cli.py
    settings.py
    browser_agent.py
    matcher.py
    tracker.py
    models.py
    utils.py
  data/
    .gitkeep
```

## Requirements

- Python 3.10+
- A Naukri account
- An OpenAI API key
- Windows, macOS, or Linux

## macOS / Linux setup

From the directory where you unzipped this project:

```bash
cd naukri-ai-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
python -m naukri_agent.cli init
```

Then edit these files:

```bash
nano .env
nano profile.json
nano answers.json
nano config.yaml
```

You can run commands directly:

```bash
python -m naukri_agent.cli login
python -m naukri_agent.cli run
python -m naukri_agent.cli report --last 50
```

Or use the helper script:

```bash
chmod +x run.sh
./run.sh login
./run.sh run
./run.sh report --last 50
```

## Windows setup

Open PowerShell in the directory where you unzipped this project:

```powershell
cd naukri-ai-agent
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
python -m naukri_agent.cli init
```

If PowerShell blocks activation scripts, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Then edit:

```powershell
notepad .env
notepad profile.json
notepad answers.json
notepad config.yaml
```

Run commands:

```powershell
python -m naukri_agent.cli login
python -m naukri_agent.cli run
python -m naukri_agent.cli report --last 50
```

Or use:

```powershell
.\run.bat login
.\run.bat run
.\run.bat report --last 50
```

## Step 1: Initialize local files

```bash
python -m naukri_agent.cli init
```

This creates:

- `.env` from `.env.example`
- `profile.json` from `profile.example.json`
- `answers.json` from `answers.example.json`
- `data/applications.csv`
- `data/browser-profile/` when the browser is first opened

Existing files are not overwritten.

## Step 2: Configure `.env`

Open `.env` and set your OpenAI API key:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

You can use a different model if your account supports it.

## Step 3: Edit `profile.json`

Update your experience, preferred roles, skills, locations, summary, industries, and companies to avoid.

Do not put your Naukri password in this file.

## Step 4: Edit `answers.json`

Add common answers for Naukri application questions. The agent only fills questions it can confidently match to known answer keys. Unknown questions are marked `needs_manual_review` by default.

Example answer keys include:

- notice period
- current ctc
- expected ctc
- reason for job change
- willing to relocate
- serving notice
- total experience
- relevant experience
- current location
- preferred location

## Step 5: Edit `config.yaml`

Add one or more Naukri search URLs under `search_urls`.

Important safe defaults:

```yaml
dry_run: true
auto_submit: false
skip_external_apply: true
skip_unknown_questions: true
skip_captcha: true
browser_headless: false
```

## Step 6: Log in manually

```bash
python -m naukri_agent.cli login
```

A visible Chromium browser opens. Log in to Naukri manually. When you are done, return to the terminal and press Enter. The browser profile is saved in:

```text
data/browser-profile
```

The next run should reuse this local session.

## Step 7: Dry run

```bash
python -m naukri_agent.cli run
```

Dry run does not click final apply/submit buttons. It scans configured search URLs, extracts jobs, asks the AI matcher to score them, and writes results to `data/applications.csv`.

## Step 8: Review report

```bash
python -m naukri_agent.cli report --last 50
```

Review scores, decisions, status, and reasons.

## Step 9: Live run without final auto-submit

```bash
python -m naukri_agent.cli run --no-dry-run
```

This opens job pages and validates flows, but it still avoids final submission unless auto-submit is enabled. Risky flows are skipped or marked for manual review.

## Step 10: Auto-submit mode

```bash
python -m naukri_agent.cli run --no-dry-run --auto-submit
```

Final submission is attempted only when all conditions pass:

- job score is at or above `min_match_score`
- job URL has not already been processed
- daily application limit is not exceeded
- not an external company form when `skip_external_apply` is true
- no CAPTCHA/security verification is detected
- no unknown required questions are detected when `skip_unknown_questions` is true
- the matcher decision is `apply`

Use this only after reviewing dry-run output.

## CSV tracker

The tracker file is:

```text
data/applications.csv
```

Columns:

- timestamp
- job_title
- company
- location
- experience
- url
- score
- decision
- status
- reason

The agent prevents duplicate processing by URL.

## How matching works

`naukri_agent.matcher.JobMatcher` sends your profile, job text, and relevant config constraints to the OpenAI SDK and asks for strict JSON:

```json
{
  "score": 0,
  "decision": "apply",
  "reason": "...",
  "risks": ["..."],
  "suggested_recruiter_note": "..."
}
```

If the model returns invalid JSON or the API call fails, the job is safely marked `needs_manual_review`.

## Troubleshooting

### Playwright browser not opening

Run:

```bash
playwright install chromium
```

If that does not work, reinstall dependencies:

```bash
pip install -r requirements.txt
playwright install chromium
```

On Linux, you may also need OS dependencies:

```bash
playwright install-deps chromium
```

### OpenAI API key error

Check that `.env` exists and contains:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

Then verify the virtual environment is active and `openai` is installed:

```bash
python -c "from openai import OpenAI; print('ok')"
```

### Naukri layout changed

Naukri frontend selectors may change. The project uses broad selectors and fallbacks, but if jobs are not found:

1. Open the search URL manually.
2. Confirm jobs are visible after login.
3. Run dry-run again.
4. If still failing, inspect `naukri_agent/browser_agent.py` and update selectors in `extract_job_cards()` and `extract_job_detail()`.

### CAPTCHA detected

The agent intentionally does not solve or bypass CAPTCHA. Log in manually, complete any verification yourself, then rerun. If CAPTCHA appears during application flow, the job is skipped or marked for manual review.

### No jobs found

Check:

- `search_urls` in `config.yaml` are valid Naukri job-search URLs.
- You are logged in via `python -m naukri_agent.cli login`.
- The search page shows job results in a normal browser.
- Your Naukri account does not require verification.

### Permission issues on Windows PowerShell

If virtual environment activation is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate again:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Browser profile problems

If the session becomes corrupted or you want to force a fresh login, close all Chromium windows and delete:

```text
data/browser-profile
```

Then run:

```bash
python -m naukri_agent.cli login
```

## Notes and limitations

- Browser automation can break when Naukri changes layout.
- One-click apply flows may behave differently across jobs; the agent is intentionally conservative.
- External company application forms are skipped by default.
- Unknown application questions are not guessed.
- This project is for your local personal workflow only. Follow Naukri's terms and use reasonable limits.
