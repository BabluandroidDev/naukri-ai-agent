from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from .models import JobPosting, MatchResult
from .settings import AgentSettings
from .utils import safe_lower


class JobMatcher:
    def __init__(self, settings: AgentSettings):
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def precheck(self, job: JobPosting) -> MatchResult | None:
        """Apply hard local constraints before spending API tokens."""
        company_lower = safe_lower(job.company)
        title_lower = safe_lower(job.title)
        location_lower = safe_lower(job.location)

        blocked = [
            str(company).strip().lower()
            for company in self.settings.config.get("blacklisted_companies", [])
            if str(company).strip()
        ]
        profile_blocked = [
            str(company).strip().lower()
            for company in self.settings.profile.get("companies_to_avoid", [])
            if str(company).strip()
        ]
        for blocked_company in blocked + profile_blocked:
            if blocked_company and blocked_company in company_lower:
                return MatchResult(
                    score=0,
                    decision="skip",
                    reason=f"Company is blacklisted or configured to avoid: {job.company}",
                    risks=["blacklisted_company"],
                )

        allowed_locations = [
            str(loc).strip().lower()
            for loc in self.settings.config.get("allowed_locations", [])
            if str(loc).strip()
        ]
        if allowed_locations and job.location:
            if not any(location in location_lower for location in allowed_locations):
                return MatchResult(
                    score=30,
                    decision="skip",
                    reason="Job location is outside configured allowed_locations.",
                    risks=["location_mismatch"],
                )

        suspicious_title_terms = ["walkin", "walk-in", "bond", "training fee", "registration fee"]
        if any(term in title_lower for term in suspicious_title_terms):
            return MatchResult(
                score=0,
                decision="needs_manual_review",
                reason="Title contains terms that may require manual verification.",
                risks=["suspicious_title"],
            )
        return None

    def match(self, job: JobPosting) -> MatchResult:
        prechecked = self.precheck(job)
        if prechecked:
            return prechecked

        if not self.client:
            return MatchResult(
                score=0,
                decision="needs_manual_review",
                reason="OPENAI_API_KEY is missing. Configure .env to enable AI matching.",
                risks=["missing_openai_api_key"],
            )

        prompt = self._build_prompt(job)
        try:
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a conservative job matching engine. "
                            "Return only valid JSON. Do not include markdown. "
                            "If data is insufficient, use decision needs_manual_review."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            result = MatchResult.model_validate(data)
            return self._enforce_threshold(job, result)
        except (json.JSONDecodeError, ValidationError) as exc:
            return MatchResult(
                score=0,
                decision="needs_manual_review",
                reason=f"AI returned invalid JSON or schema: {exc}",
                risks=["invalid_ai_output"],
            )
        except Exception as exc:  # API/network/model errors should not crash live automation.
            return MatchResult(
                score=0,
                decision="needs_manual_review",
                reason=f"AI matching failed safely: {exc}",
                risks=["ai_api_error"],
            )

    def _build_prompt(self, job: JobPosting) -> str:
        profile = self.settings.profile
        config_subset: dict[str, Any] = {
            "min_match_score": self.settings.config.get("min_match_score"),
            "allowed_locations": self.settings.config.get("allowed_locations"),
            "blacklisted_companies": self.settings.config.get("blacklisted_companies"),
            "skip_external_apply": self.settings.config.get("skip_external_apply"),
            "skip_unknown_questions": self.settings.config.get("skip_unknown_questions"),
            "skip_captcha": self.settings.config.get("skip_captcha"),
        }
        schema = {
            "score": "integer 0-100",
            "decision": "apply | skip | needs_manual_review",
            "reason": "short explanation",
            "risks": ["short risk labels"],
            "suggested_recruiter_note": "short note, empty string if not useful",
        }
        return (
            "Compare this Naukri job with my profile and constraints.\n\n"
            "Scoring guidance:\n"
            "- 90-100: excellent role, skills, experience, and location match.\n"
            "- 75-89: strong match with minor gaps.\n"
            "- 55-74: possible but not strong; usually needs_manual_review unless compelling.\n"
            "- below 55: skip.\n"
            "- If company, location, experience, role, or risk is unclear, prefer needs_manual_review.\n"
            "- Do not recommend apply when there are obvious red flags.\n\n"
            f"Return strict JSON matching this schema:\n{json.dumps(schema, indent=2)}\n\n"
            f"Profile:\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
            f"Config constraints:\n{json.dumps(config_subset, ensure_ascii=False, indent=2)}\n\n"
            f"Job:\n{job.compact_text()}\n"
        )

    def _enforce_threshold(self, job: JobPosting, result: MatchResult) -> MatchResult:
        if result.decision == "apply" and result.score < self.settings.min_match_score:
            result.decision = "skip"
            result.reason = (
                result.reason.strip()
                + f" Score {result.score} is below min_match_score {self.settings.min_match_score}."
            ).strip()
            if "below_threshold" not in result.risks:
                result.risks.append("below_threshold")
        return result
