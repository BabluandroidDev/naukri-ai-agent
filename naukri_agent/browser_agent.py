from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

from playwright.sync_api import BrowserContext, Error, Page, TimeoutError, sync_playwright

from .models import JobPosting, MatchResult
from .settings import AgentSettings
from .utils import (
    best_answer_for_question,
    is_naukri_url,
    normalize_space,
    safe_lower,
    text_contains_any,
    truncate,
)


CAPTCHA_TERMS = [
    "captcha",
    "verify you are human",
    "robot",
    "unusual traffic",
    "security check",
    "human verification",
    "are you a human",
]

EXTERNAL_TERMS = [
    "apply on company site",
    "company website",
    "external apply",
    "redirecting",
    "third party",
]

UNKNOWN_FLOW_TERMS = [
    "assessment",
    "test required",
    "upload resume",
    "upload file",
    "record video",
    "video interview",
    "screening test",
]


@dataclass(slots=True)
class ApplyOutcome:
    status: str
    reason: str


class NaukriBrowserAgent:
    def __init__(self, settings: AgentSettings):
        self.settings = settings
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.browser_profile_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def browser_context(self) -> Iterable[BrowserContext]:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.settings.browser_profile_dir),
                headless=self.settings.browser_headless,
                viewport={"width": 1366, "height": 900},
                accept_downloads=False,
            )
            try:
                yield context
            finally:
                context.close()

    def login(self) -> None:
        with self.browser_context() as context:
            page = self._new_or_first_page(context)
            page.goto("https://www.naukri.com/", wait_until="domcontentloaded", timeout=60000)
            print("A visible browser has opened. Log in manually if needed.")
            print("When you are fully logged in, return here and press Enter to save the session.")
            input("Press Enter after manual login: ")
            print(f"Session saved locally in: {self.settings.browser_profile_dir}")

    def scan_jobs(self) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        search_urls = self.settings.config.get("search_urls", [])
        with self.browser_context() as context:
            page = self._new_or_first_page(context)
            for search_url in search_urls:
                print(f"Scanning: {search_url}")
                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                    self._safe_wait(page, 2000)
                    if self.detect_captcha(page):
                        print("CAPTCHA/security verification detected on search page. Skipping this URL.")
                        continue
                    cards = self.extract_job_cards(page)
                    print(f"Found {len(cards)} candidate job cards/links.")
                    for card_job in cards:
                        if not card_job.url or card_job.url in seen:
                            continue
                        seen.add(card_job.url)
                        detailed = self.extract_job_detail(page, card_job)
                        jobs.append(detailed)
                        time.sleep(max(0.5, min(self.settings.delay_seconds_between_jobs, 5)))
                except Exception as exc:
                    print(f"Search URL failed safely: {search_url} -> {exc}")
        return jobs

    def apply_to_job(
        self,
        job: JobPosting,
        match: MatchResult,
        dry_run: bool,
        auto_submit: bool,
    ) -> ApplyOutcome:
        if dry_run:
            return ApplyOutcome("dry_run_apply_candidate", "Dry run: no browser apply action performed.")

        if not auto_submit:
            return ApplyOutcome(
                "manual_review_ready",
                "Live run without auto-submit: job is a match, but final submission is disabled.",
            )

        with self.browser_context() as context:
            page = self._new_or_first_page(context)
            try:
                page.goto(job.url, wait_until="domcontentloaded", timeout=60000)
                self._safe_wait(page, 1500)

                if self.detect_captcha(page):
                    return ApplyOutcome("skipped_captcha", "CAPTCHA/security verification detected.")
                if self.detect_external_apply(page):
                    if self.settings.config.get("skip_external_apply", True):
                        return ApplyOutcome("skipped_external_apply", "External company apply flow detected.")
                if self.detect_unknown_flow(page):
                    return ApplyOutcome("needs_manual_review", "Possible test/upload/suspicious flow detected.")

                apply_button = self.find_apply_button(page)
                if apply_button is None:
                    return ApplyOutcome("needs_manual_review", "Could not find a safe apply button.")

                # In auto-submit mode only, clicking Apply is allowed. On some Naukri jobs this may
                # submit immediately, so this path is intentionally gated by --auto-submit.
                apply_button.click(timeout=10000)
                self._safe_wait(page, 2500)

                if self.detect_captcha(page):
                    return ApplyOutcome("skipped_captcha", "CAPTCHA/security verification appeared after clicking apply.")
                if self.detect_external_apply(page) and self.settings.config.get("skip_external_apply", True):
                    return ApplyOutcome("skipped_external_apply", "External apply appeared after clicking apply.")
                if self.detect_unknown_flow(page):
                    return ApplyOutcome("needs_manual_review", "Unknown assessment/upload flow appeared.")

                form_result = self.handle_application_form(page, match.suggested_recruiter_note)
                if form_result.status != "ok":
                    return form_result

                submit_button = self.find_submit_button(page)
                if submit_button is None:
                    if self.detect_success(page):
                        return ApplyOutcome("applied", "Application appears to have been submitted successfully.")
                    return ApplyOutcome("maybe_submitted", "Clicked apply; no final submit button or success state found.")

                submit_button.click(timeout=10000)
                self._safe_wait(page, 2500)
                if self.detect_captcha(page):
                    return ApplyOutcome("skipped_captcha", "CAPTCHA/security verification appeared at submission.")
                if self.detect_success(page):
                    return ApplyOutcome("auto_submitted", "Application submitted successfully.")
                return ApplyOutcome("maybe_submitted", "Submit clicked; success confirmation was not clearly detected.")
            except TimeoutError as exc:
                return ApplyOutcome("needs_manual_review", f"Timed out during apply flow: {exc}")
            except Error as exc:
                return ApplyOutcome("needs_manual_review", f"Browser error during apply flow: {exc}")
            except Exception as exc:
                return ApplyOutcome("needs_manual_review", f"Apply flow failed safely: {exc}")

    def extract_job_cards(self, page: Page) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        selectors = [
            "article",
            ".srp-jobtuple-wrapper",
            ".cust-job-tuple",
            ".jobTuple",
            "[data-job-id]",
            "div[class*='jobTuple']",
        ]

        elements = []
        for selector in selectors:
            try:
                located = page.locator(selector)
                count = min(located.count(), 50)
                if count:
                    elements = [located.nth(i) for i in range(count)]
                    break
            except Exception:
                continue

        for element in elements:
            try:
                link = self._first_locator(
                    element,
                    [
                        "a.title",
                        "a[class*='title']",
                        "a[href*='job-listings']",
                        "a[href*='naukri.com']",
                    ],
                )
                if link is None:
                    continue
                title = normalize_space(link.inner_text(timeout=3000))
                href = link.get_attribute("href", timeout=3000) or ""
                url = urljoin(page.url, href)
                company = self._text_from_selectors(
                    element,
                    [
                        ".comp-name",
                        "a[class*='comp']",
                        ".companyName",
                        "span[class*='company']",
                        "div[class*='company']",
                    ],
                )
                location = self._text_from_selectors(
                    element,
                    [
                        ".locWdth",
                        "span[class*='loc']",
                        "li[class*='location']",
                        "span[title*='Location']",
                    ],
                )
                experience = self._text_from_selectors(
                    element,
                    [
                        ".expwdth",
                        "span[class*='exp']",
                        "li[class*='experience']",
                        "span[title*='Experience']",
                    ],
                )
                if title and url:
                    jobs.append(
                        JobPosting(
                            title=title,
                            company=company,
                            location=location,
                            experience=experience,
                            url=url,
                        )
                    )
            except Exception:
                continue

        if jobs:
            return self._unique_jobs(jobs)

        # Fallback: collect visible job links even if cards were not recognized.
        try:
            links = page.locator("a[href*='job-listings']")
            for i in range(min(links.count(), 50)):
                link = links.nth(i)
                title = normalize_space(link.inner_text(timeout=2000))
                href = link.get_attribute("href", timeout=2000) or ""
                url = urljoin(page.url, href)
                if title and url:
                    jobs.append(JobPosting(title=title, url=url))
        except Exception:
            pass
        return self._unique_jobs(jobs)

    def extract_job_detail(self, page: Page, job: JobPosting) -> JobPosting:
        detail = JobPosting(**job.model_dump())
        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=60000)
            self._safe_wait(page, 1500)
            if self.detect_captcha(page):
                detail.description = "CAPTCHA/security verification detected on job detail page."
                return detail

            title = self._text_from_page_selectors(
                page,
                [
                    "h1",
                    "h1[class*='title']",
                    ".jd-header-title",
                    ".job-title",
                ],
            )
            company = self._text_from_page_selectors(
                page,
                [
                    ".jd-header-comp-name",
                    "a[class*='comp']",
                    ".company-name",
                    "span[class*='company']",
                ],
            )
            location = self._text_from_page_selectors(
                page,
                [
                    ".location",
                    "span[class*='loc']",
                    "div[class*='location']",
                    "a[href*='jobs-in']",
                ],
            )
            experience = self._text_from_page_selectors(
                page,
                [
                    ".experience",
                    "span[class*='exp']",
                    "div[class*='experience']",
                ],
            )
            description = self._text_from_page_selectors(
                page,
                [
                    ".job-desc",
                    "section[class*='job-desc']",
                    "div[class*='description']",
                    "div[class*='jobDescription']",
                    "main",
                    "body",
                ],
                max_chars=16000,
            )
            detail.title = title or detail.title
            detail.company = company or detail.company
            detail.location = location or detail.location
            detail.experience = experience or detail.experience
            detail.description = description or detail.description
        except Exception as exc:
            detail.description = f"Failed to extract detail safely: {exc}"
        return detail

    def detect_captcha(self, page: Page) -> bool:
        try:
            text = page.locator("body").inner_text(timeout=3000)
            return text_contains_any(text, CAPTCHA_TERMS)
        except Exception:
            return False

    def detect_external_apply(self, page: Page) -> bool:
        try:
            if page.url and not is_naukri_url(page.url):
                return True
            text = page.locator("body").inner_text(timeout=3000)
            return text_contains_any(text, EXTERNAL_TERMS)
        except Exception:
            return False

    def detect_unknown_flow(self, page: Page) -> bool:
        try:
            text = page.locator("body").inner_text(timeout=3000)
            return text_contains_any(text, UNKNOWN_FLOW_TERMS)
        except Exception:
            return False

    def detect_success(self, page: Page) -> bool:
        try:
            text = safe_lower(page.locator("body").inner_text(timeout=3000))
            success_terms = [
                "successfully applied",
                "application sent",
                "applied successfully",
                "you have applied",
                "application submitted",
            ]
            return any(term in text for term in success_terms)
        except Exception:
            return False

    def find_apply_button(self, page: Page):
        selectors = [
            "button:has-text('Apply')",
            "a:has-text('Apply')",
            "button[id*='apply']",
            "button[class*='apply']",
            "a[class*='apply']",
        ]
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible(timeout=2000):
                    text = safe_lower(locator.inner_text(timeout=2000))
                    if "apply" in text and "applied" not in text:
                        return locator
            except Exception:
                continue
        return None

    def find_submit_button(self, page: Page):
        selectors = [
            "button:has-text('Submit')",
            "button:has-text('Send')",
            "button:has-text('Apply')",
            "button[type='submit']",
            "input[type='submit']",
        ]
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible(timeout=2000):
                    text = safe_lower(locator.inner_text(timeout=2000))
                    if any(term in text for term in ["submit", "send", "apply", "continue"]):
                        return locator
            except Exception:
                continue
        return None

    def handle_application_form(self, page: Page, recruiter_note: str) -> ApplyOutcome:
        """Fill only known fields. Unknown required fields cause manual review."""
        if self.detect_unknown_flow(page):
            return ApplyOutcome("needs_manual_review", "Detected test/upload/suspicious form content.")

        unknown_required: list[str] = []
        answered = 0

        # Textareas often hold recruiter notes or screening questions.
        try:
            textareas = page.locator("textarea")
            for i in range(min(textareas.count(), 10)):
                field = textareas.nth(i)
                if not field.is_visible(timeout=1000):
                    continue
                label = self._label_for_input(page, field)
                answer = best_answer_for_question(label, self.settings.answers)
                if not answer and recruiter_note and self._looks_like_recruiter_note(label):
                    answer = recruiter_note
                if answer:
                    field.fill(answer[:900], timeout=3000)
                    answered += 1
                elif self._is_required(field):
                    unknown_required.append(label or "required textarea")
        except Exception:
            pass

        # Inputs for common salary/location/experience questions.
        try:
            inputs = page.locator("input:not([type='hidden']):not([type='file']):not([type='checkbox']):not([type='radio'])")
            for i in range(min(inputs.count(), 20)):
                field = inputs.nth(i)
                if not field.is_visible(timeout=1000):
                    continue
                current_value = field.input_value(timeout=1000)
                if current_value:
                    continue
                label = self._label_for_input(page, field)
                answer = best_answer_for_question(label, self.settings.answers)
                if answer:
                    field.fill(answer[:250], timeout=3000)
                    answered += 1
                elif self._is_required(field):
                    unknown_required.append(label or "required input")
        except Exception:
            pass

        # Selects: choose exact/partial answer only when available, never guess.
        try:
            selects = page.locator("select")
            for i in range(min(selects.count(), 10)):
                field = selects.nth(i)
                if not field.is_visible(timeout=1000):
                    continue
                label = self._label_for_input(page, field)
                answer = best_answer_for_question(label, self.settings.answers)
                if answer and self._select_option_safely(field, answer):
                    answered += 1
                elif self._is_required(field):
                    unknown_required.append(label or "required select")
        except Exception:
            pass

        if unknown_required and self.settings.config.get("skip_unknown_questions", True):
            return ApplyOutcome(
                "needs_manual_review",
                "Unknown required questions detected: " + "; ".join(unknown_required[:5]),
            )
        return ApplyOutcome("ok", f"Known application fields handled: {answered}")

    def _new_or_first_page(self, context: BrowserContext) -> Page:
        if context.pages:
            return context.pages[0]
        return context.new_page()

    def _safe_wait(self, page: Page, milliseconds: int) -> None:
        try:
            page.wait_for_timeout(milliseconds)
        except Exception:
            time.sleep(milliseconds / 1000)

    def _first_locator(self, root, selectors: list[str]):
        for selector in selectors:
            try:
                located = root.locator(selector).first
                if located.count():
                    return located
            except Exception:
                continue
        return None

    def _text_from_selectors(self, root, selectors: list[str], max_chars: int = 500) -> str:
        for selector in selectors:
            try:
                located = root.locator(selector).first
                if located.count():
                    text = normalize_space(located.inner_text(timeout=2000))
                    if text:
                        return truncate(text, max_chars)
            except Exception:
                continue
        return ""

    def _text_from_page_selectors(self, page: Page, selectors: list[str], max_chars: int = 500) -> str:
        return self._text_from_selectors(page, selectors, max_chars=max_chars)

    def _unique_jobs(self, jobs: list[JobPosting]) -> list[JobPosting]:
        seen: set[str] = set()
        unique: list[JobPosting] = []
        for job in jobs:
            if not job.url or job.url in seen:
                continue
            seen.add(job.url)
            unique.append(job)
        return unique

    def _label_for_input(self, page: Page, field) -> str:
        pieces: list[str] = []
        try:
            placeholder = field.get_attribute("placeholder", timeout=1000)
            if placeholder:
                pieces.append(placeholder)
        except Exception:
            pass
        try:
            aria = field.get_attribute("aria-label", timeout=1000)
            if aria:
                pieces.append(aria)
        except Exception:
            pass
        try:
            field_id = field.get_attribute("id", timeout=1000)
            if field_id:
                label = page.locator(f"label[for='{field_id}']").first
                if label.count():
                    pieces.append(label.inner_text(timeout=1000))
        except Exception:
            pass
        try:
            parent_text = field.locator("xpath=ancestor::*[self::label or self::div or self::li][1]").inner_text(timeout=1000)
            if parent_text:
                pieces.append(parent_text)
        except Exception:
            pass
        return truncate(normalize_space(" ".join(pieces)), 300)

    def _looks_like_recruiter_note(self, label: str) -> bool:
        label = safe_lower(label)
        terms = ["cover", "note", "message", "recruiter", "why should", "describe yourself"]
        return any(term in label for term in terms)

    def _is_required(self, field) -> bool:
        try:
            required = field.get_attribute("required", timeout=1000)
            aria_required = field.get_attribute("aria-required", timeout=1000)
            return required is not None or safe_lower(aria_required) == "true"
        except Exception:
            return False

    def _select_option_safely(self, field, answer: str) -> bool:
        try:
            options = field.locator("option")
            answer_lower = safe_lower(answer)
            for i in range(min(options.count(), 50)):
                option = options.nth(i)
                label = normalize_space(option.inner_text(timeout=1000))
                value = option.get_attribute("value", timeout=1000) or label
                if safe_lower(label) in answer_lower or answer_lower in safe_lower(label):
                    field.select_option(value=value, timeout=3000)
                    return True
        except Exception:
            return False
        return False
