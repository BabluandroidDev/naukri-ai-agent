# 🤖 Naukri AI Agent

> A local, AI-assisted job discovery and application workflow for Naukri, combining **browser automation, LLM-based job matching, configurable rules, conservative application handling, and local application tracking**.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Playwright-Browser%20Automation-2EAD33?style=for-the-badge&logo=playwright&logoColor=white" alt="Playwright">
  <img src="https://img.shields.io/badge/OpenAI-LLM%20Matching-412991?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI">
  <img src="https://img.shields.io/badge/Pydantic-Validation-E92063?style=for-the-badge&logo=pydantic&logoColor=white" alt="Pydantic">
  <img src="https://img.shields.io/badge/CLI-Python%20CLI-111111?style=for-the-badge" alt="CLI">
</p>

<p align="center">
  <strong>Discover → Extract → Match → Review → Apply → Track</strong>
</p>

---

## 📌 Overview

**Naukri AI Agent** is a local automation tool that helps streamline repetitive job-search and application workflows on Naukri.

Instead of treating every job equally, the system:

1. Opens Naukri in a real visible Chromium browser
2. Scans configured job-search pages
3. Extracts job title, company, location, experience, URL, and description
4. Applies local constraints before using the LLM
5. Sends eligible jobs to an OpenAI-powered matching engine
6. Produces a structured match score and decision
7. Handles only known application fields
8. Safely stops when a flow requires manual intervention
9. Records processed jobs in a local CSV tracker

The design is intentionally **conservative and human-controlled**, with dry-run mode enabled by default.

---

# 🧠 Core Idea

```text
                Naukri Search Pages
                        │
                        ▼
              ┌───────────────────┐
              │ Browser Automation │
              │    Playwright      │
              └─────────┬─────────┘
                        │
                        ▼
                 Job Extraction
                        │
                        ▼
              ┌───────────────────┐
              │ Local Prechecks   │
              │ • Location        │
              │ • Company         │
              │ • Risk terms      │
              └─────────┬─────────┘
                        │
                        ▼
               ┌────────────────┐
               │  AI Job Matcher │
               │     OpenAI      │
               └───────┬────────┘
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
          SKIP / REVIEW         APPLY
                                 │
                                 ▼
                       Application Flow
                                 │
                  ┌──────────────┼─────────────┐
                  ▼              ▼             ▼
              CAPTCHA        Unknown      External Site
                  │           Question          │
                  └────────────┴─────────────────┘
                               │
                               ▼
                        Manual Review
                               │
                               ▼
                       applications.csv
```

---

# ✨ Features

## 🔎 Job Discovery

Configure multiple Naukri search URLs and scan them automatically.

Example:

```yaml
search_urls:
  - "https://www.naukri.com/android-developer-jobs"
  - "https://www.naukri.com/full-stack-developer-jobs"
  - "https://www.naukri.com/mobile-app-engineer-jobs"
  - "https://www.naukri.com/flutter-developer-jobs"
```

The agent extracts candidate job listings and removes duplicate URLs before processing them.

---

## 🧩 Job Detail Extraction

For each candidate listing, the browser agent attempts to collect:

* Job title
* Company
* Location
* Experience
* Job description
* Job URL

The extracted data is normalized into a typed `JobPosting` model before entering the matching pipeline.

---

# 🧠 AI-Powered Job Matching

The project uses the OpenAI Python SDK to evaluate a job against a configurable candidate profile.

The matcher returns structured output:

```json
{
  "score": 0,
  "decision": "apply",
  "reason": "short explanation",
  "risks": [],
  "suggested_recruiter_note": ""
}
```

### Supported decisions

```text
apply
skip
needs_manual_review
```

The model is instructed to prefer manual review when information is insufficient or risky.

---

# 🎯 Matching Strategy

The agent does not immediately send every scraped job to the LLM.

A local precheck runs first.

### Local constraints

```text
Company blacklist
        ↓
Location restrictions
        ↓
Suspicious title detection
        ↓
AI matching
```

The current implementation can reject or review jobs based on:

* Blacklisted companies
* Configured locations
* Walk-in roles
* Bond-related roles
* Training-fee language
* Registration-fee language

This reduces unnecessary model calls and creates a deterministic safety layer before AI evaluation.

---

# 📊 Match Scoring

The AI matcher uses a 0–100 score.

Current guidance:

|  Score | Interpretation          |
| -----: | ----------------------- |
| 90–100 | Excellent match         |
|  75–89 | Strong match            |
|  55–74 | Possible match / review |
|   < 55 | Skip                    |

The configured minimum match threshold is currently:

```yaml
min_match_score: 75
```

A result marked `apply` below this threshold is converted into `skip`.

---

# 🛡️ Safety-First Design

Automation is intentionally constrained instead of attempting to bypass website protections.

## CAPTCHA Protection

The agent detects terms associated with:

* CAPTCHA
* Human verification
* Robot checks
* Security checks
* Unusual traffic

Detected verification flows are skipped or sent for manual review.

---

## 🚫 No CAPTCHA Bypass

The project does not attempt to solve, bypass, or evade CAPTCHA/security verification.

---

## 🌐 External Application Protection

External application flows can be skipped automatically.

For example:

```text
Naukri Job
    ↓
Apply
    ↓
External Company Website
    ↓
Manual Review / Skip
```

This behavior is controlled by:

```yaml
skip_external_apply: true
```

---

## ❓ Unknown Question Protection

The agent only fills application questions when it can confidently match them to configured answers.

Unknown required questions can trigger:

```text
needs_manual_review
```

instead of guessing.

---

## 👤 Manual Login

The application does not store a Naukri password.

Login is performed manually inside a visible Chromium browser, after which the local browser session can be reused.

---

# 🔐 Execution Modes

The project supports three practical workflows.

## 1. Dry Run — Recommended First Step

Default:

```yaml
dry_run: true
auto_submit: false
```

Command:

```bash
python -m naukri_agent.cli run
```

In dry-run mode:

* Jobs are scanned
* Jobs are scored
* Decisions are generated
* Results are tracked
* Final application actions are not performed

---

## 2. Live Validation Without Auto Submit

```bash
python -m naukri_agent.cli run --no-dry-run
```

This enables the browser application flow for matched jobs while keeping final submission disabled unless auto-submit is explicitly enabled.

---

## 3. Auto Submit

```bash
python -m naukri_agent.cli run --no-dry-run --auto-submit
```

Auto-submit is intentionally opt-in.

The system checks configured thresholds and safety conditions before continuing with the application flow.

---

# 🧾 Application Question Handling

The agent can match visible application questions against known answers.

Supported categories include examples such as:

```text
Notice period
Current CTC
Expected CTC
Reason for job change
Willing to relocate
Serving notice
Total experience
Relevant experience
Current location
Preferred location
```

Matching uses normalized question text and conservative synonym handling instead of blindly filling unknown fields.

---

# 📝 Recruiter Note Generation

The AI matcher can also return:

```json
{
  "suggested_recruiter_note": "..."
}
```

When the application form contains a field that looks like:

* Cover
* Note
* Message
* Recruiter message
* Why should you be considered
* Describe yourself

the generated note can be used when appropriate.

---

# 📦 Application Tracking

Every processed job is recorded locally in:

```text
data/applications.csv
```

The tracker stores:

| Field        | Description                   |
| ------------ | ----------------------------- |
| `timestamp`  | Processing time               |
| `job_title`  | Job title                     |
| `company`    | Company                       |
| `location`   | Location                      |
| `experience` | Experience requirement        |
| `url`        | Job URL                       |
| `score`      | AI match score                |
| `decision`   | AI decision                   |
| `status`     | Processing/application status |
| `reason`     | Explanation                   |

Duplicate processing is prevented by job URL.

---

# 📈 Daily Application Guard

A hard daily application limit can be configured:

```yaml
max_applications_per_day: 10
```

Once the configured limit is reached, additional submissions are blocked for the local day.

---

# ⚙️ Configuration

Main configuration lives in:

```text
config.yaml
```

Example:

```yaml
search_urls:
  - "https://www.naukri.com/android-developer-jobs"
  - "https://www.naukri.com/mobile-app-engineer-jobs"

min_match_score: 75

max_applications_per_day: 10

allowed_locations:
  - "Remote"
  - "Bengaluru"
  - "Hyderabad"
  - "Pune"
  - "Mumbai"
  - "Delhi NCR"

blacklisted_companies: []

auto_submit: false
dry_run: true

skip_external_apply: true
skip_unknown_questions: true
skip_captcha: true

browser_headless: false

delay_seconds_between_jobs: 8
```

---

# 👤 Candidate Profile

The matching engine reads candidate preferences from:

```text
profile.json
```

This file can define:

* Experience
* Preferred roles
* Skills
* Preferred locations
* Work-mode preference
* Industry preferences
* Companies to avoid
* Resume summary

Example structure:

```json
{
  "name": "Candidate Name",
  "total_experience_years": 5,
  "preferred_roles": [
    "Android Developer",
    "Mobile App Engineer"
  ],
  "skills": [
    "Kotlin",
    "Java",
    "Android",
    "Flutter",
    "Python",
    "REST APIs"
  ],
  "preferred_locations": [
    "Remote",
    "Bengaluru",
    "Hyderabad"
  ]
}
```

> Keep personal career data and compensation information out of a public repository. Use an example file for public sharing.

---

# 🗂️ Project Structure

```text
naukri-ai-agent/
│
├── README.md
├── requirements.txt
├── config.yaml
│
├── profile.json
├── answers.json
├── .env
│
├── run.sh
├── run.bat
│
├── naukri_agent/
│   ├── __init__.py
│   ├── cli.py
│   ├── settings.py
│   ├── browser_agent.py
│   ├── matcher.py
│   ├── tracker.py
│   ├── models.py
│   └── utils.py
│
└── data/
    ├── applications.csv
    └── browser-profile/
```

---

# 🧱 Architecture Responsibilities

### `cli.py`

Command-line entry point.

Handles:

```text
init
login
run
report
```

and orchestrates the overall workflow.

### `settings.py`

Loads and validates:

* YAML configuration
* Environment variables
* Candidate profile
* Application answers

and exposes them through `AgentSettings`.

### `browser_agent.py`

Responsible for browser automation:

* Manual login
* Persistent browser context
* Job discovery
* Job detail extraction
* Apply-button handling
* Form handling
* CAPTCHA detection
* External-apply detection
* Unknown-flow detection
* Submission confirmation

### `matcher.py`

Responsible for AI-assisted job matching.

Pipeline:

```text
Hard Precheck
     ↓
OpenAI Request
     ↓
JSON Parse
     ↓
Pydantic Validation
     ↓
Threshold Enforcement
     ↓
MatchResult
```

### `models.py`

Defines typed Pydantic models:

```text
JobPosting
MatchResult
ApplicationLogRow
```

### `tracker.py`

Provides local CSV-based application tracking and duplicate detection.

### `utils.py`

Contains reusable helpers for:

* JSON handling
* Environment values
* Text normalization
* URL validation
* Question normalization
* Conservative answer matching

---

# 🛠️ Tech Stack

| Technology    | Purpose                   |
| ------------- | ------------------------- |
| Python        | Core application          |
| Playwright    | Browser automation        |
| Chromium      | Visible browser execution |
| OpenAI SDK    | LLM-based job matching    |
| Pydantic      | Typed validation          |
| PyYAML        | YAML configuration        |
| python-dotenv | Environment configuration |
| Pandas        | Data processing support   |
| CSV           | Application tracking      |

---

# 🚀 Installation

## Requirements

* Python 3.10+
* Naukri account
* OpenAI API key
* Windows, macOS, or Linux

---

## 1. Clone

```bash
git clone https://github.com/BabluandroidDev/naukri-ai-agent.git
cd naukri-ai-agent
```

---

## 2. Create Virtual Environment

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

---

## 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Install Chromium

```bash
playwright install chromium
```

---

# 🔑 Environment Configuration

Create a local `.env` file:

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
```

Never commit a real API key.

---

# ▶️ Usage

## Initialize

```bash
python -m naukri_agent.cli init
```

This initializes the local configuration and tracker files.

---

## Login

```bash
python -m naukri_agent.cli login
```

A visible Chromium window opens.

Log in manually to Naukri and return to the terminal when complete.

The browser session is stored locally under:

```text
data/browser-profile/
```

---

## Run Dry Mode

```bash
python -m naukri_agent.cli run
```

This is the recommended first execution mode.

---

## Generate Report

```bash
python -m naukri_agent.cli report --last 50
```

---

## Run Helper Script

### macOS / Linux

```bash
chmod +x run.sh

./run.sh login
./run.sh run
./run.sh report --last 50
```

### Windows

```powershell
.\run.bat login
.\run.bat run
.\run.bat report --last 50
```

---

# 🔄 End-to-End Workflow

```text
1. Initialize
      ↓
2. Configure profile
      ↓
3. Configure answers
      ↓
4. Configure search URLs
      ↓
5. Manual Naukri login
      ↓
6. Scan job listings
      ↓
7. Extract job details
      ↓
8. Apply local constraints
      ↓
9. AI match + score
      ↓
10. Decide:
       ├── Skip
       ├── Manual Review
       └── Apply Candidate
      ↓
11. Handle application flow
      ↓
12. Track result in CSV
      ↓
13. Generate report
```

---

# 🧪 Error Handling

The system is designed to fail safely around several external failure conditions.

Examples include:

* Browser timeout
* Playwright errors
* Naukri layout changes
* CAPTCHA/security verification
* External application flows
* Unknown required questions
* Invalid AI JSON
* OpenAI API failures
* Missing API credentials
* Missing safe apply button

Instead of crashing the complete workflow, many of these conditions are converted into a review/skip state.

---

# 🛡️ Design Principles

### Human in the Loop

The system is designed to assist repetitive work while keeping important decisions visible and configurable.

### Conservative Automation

Unknown or suspicious flows are not guessed through.

### Separation of Concerns

```text
CLI
 ↓
Settings
 ↓
Browser Agent
 ↓
Matcher
 ↓
Models
 ↓
Tracker
```

### Configuration over Hardcoding

Candidate profile, answers, URLs, thresholds, locations, and safety controls are externalized into configuration files.

### Auditable Processing

Every processed job is written to a local tracker with decision, score, status, and reason.

---

# ⚠️ Limitations

Browser automation depends on the current Naukri frontend structure.

Changes to:

* DOM structure
* CSS selectors
* Job-card layout
* Apply flows
* Form fields
* Verification systems

may require updates to the browser automation layer.

The project intentionally does not attempt to bypass CAPTCHA or other security verification.

External company application flows are skipped by default.

Unknown required application questions are not guessed.

---

# 🧭 Future Improvements

Potential next steps for evolving the project into a more robust job-intelligence platform:

## Matching

* Skill taxonomy
* Semantic skill matching
* Experience-aware scoring
* Salary compatibility
* Role-specific weighting
* Explainable score breakdown

## Data

* SQLite instead of CSV
* Job history persistence
* Application analytics
* Search-result deduplication
* Job freshness tracking

## AI

* Structured outputs with stronger schemas
* Candidate-specific recruiter messaging
* Resume-to-JD comparison
* Skill-gap detection
* Interview preparation generation

## Engineering

* Unit tests
* Integration tests
* Browser automation tests
* CI/CD
* Structured logging
* Retry/backoff strategy
* Better observability
* Plugin-style platform adapters

## Multi-platform Architecture

A future architecture could isolate platform-specific automation:

```text
                Job Intelligence Core
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
     Naukri          LinkedIn         Other Sources
     Adapter           Adapter           Adapter
        │                │                │
        └────────────────┼────────────────┘
                         ▼
                  Common Job Model
                         ▼
                    AI Matcher
                         ▼
                 Application Tracker
```

---

# 📜 Responsible Use

This project is intended for **personal workflow automation and experimentation**.

Before using browser automation on any platform:

* Review the platform's current terms and policies.
* Use reasonable request/application limits.
* Keep credentials and session data local.
* Do not attempt to bypass CAPTCHA or security controls.
* Review automated submissions carefully.
* Do not submit inaccurate application information.

---

# 👨‍💻 Author

## Bablu Gupta

**Senior Android Developer | Software Engineer**

🌐 Portfolio
https://babluandroiddev.github.io

🐙 GitHub
https://github.com/BabluandroidDev

---

<p align="center">
  <strong>Discover smarter. Match carefully. Automate responsibly.</strong>
</p>
