import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Annotated, Any
from urllib.parse import urljoin, urlparse

import httpx
from bson import ObjectId
from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.object_id import parse_object_id
from app.db.dependencies import get_database
from app.repositories.crawl_job_repository import CrawlJobRepository
from app.repositories.enrichment_repository import EnrichmentRepository
from app.repositories.lead_repository import LeadRepository
from app.repositories.model_repository import ModelRepository
from app.schemas.auth import UserResponse
from app.schemas.enrichment import FeatureSnapshot, LeadEnrichmentSummary, PageSnapshot
from app.schemas.jobs import CrawlJob
from app.schemas.lead import EnrichmentStatus, LeadDetail, LeadScoreResponse, PipelineStatus, ScoreBreakdown
from app.services.models import ModelService


class ExtractedHtml:
    def __init__(
        self,
        *,
        title: str | None,
        meta_description: str | None,
        text: str,
        links: list[str],
        forms: int,
    ):
        self.title = title
        self.meta_description = meta_description
        self.text = text
        self.links = links
        self.forms = forms


class UsefulHtmlParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title: str | None = None
        self.meta_description: str | None = None
        self.links: list[str] = []
        self.forms = 0
        self._in_title = False
        self._skip_depth = 0
        self._text_parts: list[str] = []
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value for key, value in attrs if value is not None}
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if name in {"description", "og:description"} and attrs_dict.get("content"):
                self.meta_description = self.meta_description or attrs_dict["content"].strip()
        if tag in {"a", "link"} and attrs_dict.get("href"):
            self.links.append(urljoin(self.base_url, attrs_dict["href"]))
        if tag == "form":
            self.forms += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._in_title:
            self._title_parts.append(cleaned)
        if not self._skip_depth:
            self._text_parts.append(cleaned)

    def finish(self) -> ExtractedHtml:
        title = " ".join(self._title_parts).strip() or self.title
        text = " ".join(self._text_parts)
        text = re.sub(r"\s+", " ", text).strip()
        return ExtractedHtml(
            title=title[:240] if title else None,
            meta_description=self.meta_description[:500] if self.meta_description else None,
            text=text[:6000],
            links=list(dict.fromkeys(self.links))[:120],
            forms=self.forms,
        )


BOOKING_PROVIDERS = {
    "thefork": ["thefork", "eltenedor"],
    "covermanager": ["covermanager"],
    "opentable": ["opentable"],
    "reservas": ["reservas", "reservation", "reserve", "booking", "book a table", "mesa"],
}


class EnrichmentService:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.leads = LeadRepository(database)
        self.enrichment = EnrichmentRepository(database)
        self.jobs = CrawlJobRepository(database)
        self.models = ModelService(ModelRepository(database))

    async def enrich_lead(self, lead_id: str, current_user: UserResponse) -> LeadEnrichmentSummary:
        object_id = parse_object_id(lead_id)
        lead = await self._get_lead(object_id)
        await self.leads.update_enrichment_state(
            object_id,
            enrichment_status=EnrichmentStatus.RUNNING,
            last_enriched_at=lead.lastEnrichedAt,
            last_enrichment_error=None,
        )
        job = await self.jobs.create_running_job(
            job_type="ENRICHMENT",
            source_type="website",
            triggered_by=current_user.username,
            metadata={"leadId": lead_id, "leadName": lead.name},
        )
        job_id = ObjectId(job["id"])

        page_snapshot: dict[str, Any] | None = None
        error_message: str | None = None
        try:
            target_url = self._select_target_url(lead)
            extracted: ExtractedHtml | None = None
            http_status: int | None = None
            content_type: str | None = None

            if target_url:
                try:
                    async with httpx.AsyncClient(
                        follow_redirects=True,
                        timeout=httpx.Timeout(10.0),
                        headers={"User-Agent": "FudiLeadLab/1.0 enrichment"},
                    ) as client:
                        response = await client.get(target_url)
                    http_status = response.status_code
                    content_type = response.headers.get("content-type")
                    if response.is_success and "html" in (content_type or "").lower():
                        parser = UsefulHtmlParser(str(response.url))
                        parser.feed(response.text[:1_000_000])
                        extracted = parser.finish()
                    else:
                        error_message = f"Website fetch returned HTTP {response.status_code}."
                except httpx.HTTPError as exc:
                    error_message = f"Website fetch failed: {exc.__class__.__name__}."

                page_snapshot = await self.enrichment.create_page_snapshot(
                    lead_id=object_id,
                    url=target_url,
                    snapshot_type="website",
                    http_status=http_status,
                    content_type=content_type,
                    title=extracted.title if extracted else None,
                    meta_description=extracted.meta_description if extracted else None,
                    text_extract=extracted.text if extracted else None,
                )
            else:
                error_message = None

            features = self._build_features(lead, target_url, extracted, error_message)
            derived_signals = self._build_derived_signals(features)
            source_snapshot_ids = [page_snapshot["id"]] if page_snapshot else []
            feature_snapshot = await self.enrichment.create_feature_snapshot(
                lead_id=object_id,
                version=1,
                features=features,
                derived_signals=derived_signals,
                source_snapshot_ids=source_snapshot_ids,
            )
            score_breakdown, confidence = self._score_from_features(lead, features, derived_signals)
            await self.leads.update_score(object_id, score_breakdown=score_breakdown, confidence=confidence)

            completed_at = datetime.now(UTC)
            final_status = EnrichmentStatus.FAILED if error_message and features["brokenWebsiteHint"] else EnrichmentStatus.COMPLETED
            await self.leads.update_enrichment_state(
                object_id,
                enrichment_status=final_status,
                last_enriched_at=completed_at,
                last_enrichment_error=error_message if final_status == EnrichmentStatus.FAILED else None,
            )
            completed_job = await self.jobs.complete_job(
                job_id,
                processed_count=1,
                created_lead_count=0,
                updated_lead_count=1,
                error_count=1 if final_status == EnrichmentStatus.FAILED else 0,
                error_message=error_message if final_status == EnrichmentStatus.FAILED else None,
            )
            if final_status == EnrichmentStatus.COMPLETED:
                try:
                    await self.models.predict_lead(lead_id, current_user, trigger_type="enrichment")
                except Exception:
                    pass
            return await self._summary_from_documents(
                object_id=object_id,
                status=final_status,
                last_enriched_at=completed_at,
                last_error=error_message if final_status == EnrichmentStatus.FAILED else None,
                feature_snapshot=feature_snapshot,
                page_snapshot=page_snapshot,
                job=completed_job,
            )
        except Exception as exc:
            message = f"Enrichment failed: {exc.__class__.__name__}."
            await self.leads.update_enrichment_state(
                object_id,
                enrichment_status=EnrichmentStatus.FAILED,
                last_enriched_at=datetime.now(UTC),
                last_enrichment_error=message,
            )
            failed_job = await self.jobs.fail_job(job_id, message)
            return await self._summary_from_documents(
                object_id=object_id,
                status=EnrichmentStatus.FAILED,
                last_enriched_at=datetime.now(UTC),
                last_error=message,
                feature_snapshot=None,
                page_snapshot=page_snapshot,
                job=failed_job,
            )

    async def get_summary(self, lead_id: str) -> LeadEnrichmentSummary:
        object_id = parse_object_id(lead_id)
        lead = await self._get_lead(object_id)
        feature_snapshot = await self.enrichment.get_latest_feature_snapshot(object_id)
        page_snapshot = await self.enrichment.get_latest_page_snapshot(object_id)
        return await self._summary_from_documents(
            object_id=object_id,
            status=lead.enrichmentStatus,
            last_enriched_at=lead.lastEnrichedAt,
            last_error=lead.lastEnrichmentError,
            feature_snapshot=feature_snapshot,
            page_snapshot=page_snapshot,
            job=None,
        )

    async def list_feature_snapshots(self, lead_id: str) -> list[FeatureSnapshot]:
        object_id = parse_object_id(lead_id)
        await self._get_lead(object_id)
        snapshots = await self.enrichment.list_feature_snapshots(object_id)
        return [FeatureSnapshot.model_validate(snapshot) for snapshot in snapshots]

    async def list_page_snapshots(self, lead_id: str) -> list[PageSnapshot]:
        object_id = parse_object_id(lead_id)
        await self._get_lead(object_id)
        snapshots = await self.enrichment.list_page_snapshots(object_id)
        return [PageSnapshot.model_validate(snapshot) for snapshot in snapshots]

    async def _get_lead(self, object_id: ObjectId) -> LeadDetail:
        document = await self.leads.get_lead(object_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return LeadDetail.model_validate(document)

    async def _summary_from_documents(
        self,
        *,
        object_id: ObjectId,
        status: EnrichmentStatus,
        last_enriched_at: datetime | None,
        last_error: str | None,
        feature_snapshot: dict[str, Any] | None,
        page_snapshot: dict[str, Any] | None,
        job: dict[str, Any] | None,
    ) -> LeadEnrichmentSummary:
        lead = await self._get_lead(object_id)
        return LeadEnrichmentSummary(
            leadId=lead.id,
            status=status,
            lastEnrichedAt=last_enriched_at,
            lastError=last_error,
            latestFeatureSnapshot=FeatureSnapshot.model_validate(feature_snapshot) if feature_snapshot else None,
            latestPageSnapshot=PageSnapshot.model_validate(page_snapshot) if page_snapshot else None,
            job=CrawlJob.model_validate(job) if job else None,
            score=LeadScoreResponse(
                leadId=lead.id,
                scoreBreakdown=lead.scoreBreakdown,
                priorityScore=lead.priorityScore,
                fitScore=lead.fitScore,
                confidence=lead.confidence,
            ),
        )

    def _select_target_url(self, lead: LeadDetail) -> str | None:
        if not lead.website:
            return None
        value = lead.website.strip()
        if not value:
            return None
        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"
        return value

    def _build_features(
        self,
        lead: LeadDetail,
        target_url: str | None,
        extracted: ExtractedHtml | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        links = extracted.links if extracted else []
        title = extracted.title if extracted else ""
        meta_description = extracted.meta_description if extracted else ""
        body_text = extracted.text if extracted else ""
        text = f"{title or ''} {meta_description or ''} {body_text or ''}".lower()
        link_text = " ".join(links).lower()
        combined = f"{text} {link_text}"
        has_instagram = bool(lead.instagram) or "instagram.com" in combined
        has_facebook = "facebook.com" in combined or "fb.com" in combined
        has_email = bool(lead.email) or bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", combined))
        has_phone = bool(lead.phone) or bool(re.search(r"(\+?\d[\d\s().-]{7,}\d)", combined))
        has_contact_form = bool(extracted and extracted.forms) or "contact" in combined or "contacto" in combined
        has_menu_link = any(word in combined for word in ["menu", "carta", "menú"])
        booking_provider = self._detect_booking_provider(combined)
        has_booking_link = booking_provider is not None
        text_length = len(extracted.text) if extracted else 0
        has_website = target_url is not None and not error_message

        contactability_score = 15
        contactability_reasons: list[str] = []
        if has_phone:
            contactability_score += 25
            contactability_reasons.append("Phone detected.")
        if has_email:
            contactability_score += 25
            contactability_reasons.append("Email detected.")
        if has_contact_form:
            contactability_score += 15
            contactability_reasons.append("Contact page or form detected.")
        if has_booking_link:
            contactability_score += 15
            contactability_reasons.append("Booking flow detected.")
        if has_instagram:
            contactability_score += 5
            contactability_reasons.append("Instagram presence detected.")
        contactability_score = min(contactability_score, 100)
        if not contactability_reasons:
            contactability_reasons.append("No strong contact channel detected.")

        return {
            "hasWebsite": bool(has_website),
            "hasInstagram": has_instagram,
            "hasFacebook": has_facebook,
            "hasPhone": has_phone,
            "hasEmail": has_email,
            "hasContactForm": has_contact_form,
            "hasMenuLink": has_menu_link,
            "hasBookingLink": has_booking_link,
            "bookingProviderHint": booking_provider,
            "lowContentWebsite": bool(has_website and text_length < 800),
            "brokenWebsiteHint": bool(target_url and error_message),
            "socialOnlyPresenceHint": bool(not target_url and has_instagram),
            "openingSoonHint": any(word in combined for word in ["opening soon", "proximamente", "próximamente", "coming soon"]),
            "newOpeningHint": any(word in combined for word in ["new opening", "grand opening", "nueva apertura", "newly opened"]),
            "comingSoonHint": any(word in combined for word in ["coming soon", "proximamente", "próximamente"]),
            "contactabilityScore": contactability_score,
            "contactabilityReasons": contactability_reasons,
            "analyzedUrl": target_url,
            "linkCount": len(links),
            "textLength": text_length,
        }

    def _build_derived_signals(self, features: dict[str, Any]) -> dict[str, Any]:
        digital_maturity = "healthy"
        if features["brokenWebsiteHint"]:
            digital_maturity = "broken"
        elif features["socialOnlyPresenceHint"]:
            digital_maturity = "social_only"
        elif features["lowContentWebsite"]:
            digital_maturity = "thin_content"
        elif not features["hasWebsite"]:
            digital_maturity = "missing_website"

        novelty = "normal"
        if features["openingSoonHint"] or features["comingSoonHint"]:
            novelty = "opening_soon"
        elif features["newOpeningHint"]:
            novelty = "new_opening"

        return {
            "digitalMaturity": digital_maturity,
            "novelty": novelty,
            "contactability": "strong" if features["contactabilityScore"] >= 70 else "medium"
            if features["contactabilityScore"] >= 45
            else "weak",
        }

    def _detect_booking_provider(self, combined_text: str) -> str | None:
        for provider, needles in BOOKING_PROVIDERS.items():
            if any(needle in combined_text for needle in needles):
                return provider
        return None

    def _score_from_features(
        self,
        lead: LeadDetail,
        features: dict[str, Any],
        derived_signals: dict[str, Any],
    ) -> tuple[ScoreBreakdown, int]:
        explanation: list[str] = []
        newness_score = 65 if lead.pipelineStatus == PipelineStatus.DETECTED else 50
        if derived_signals["novelty"] in {"opening_soon", "new_opening"}:
            newness_score = 85
            explanation.append("New or upcoming opening language detected.")

        digital_gap_score = 30
        if not features["hasWebsite"]:
            digital_gap_score += 30
            explanation.append("No website detected.")
        if features["brokenWebsiteHint"]:
            digital_gap_score += 25
            explanation.append("Website appears broken or unreachable.")
        if features["lowContentWebsite"]:
            digital_gap_score += 18
            explanation.append("Website has low content depth.")
        if features["socialOnlyPresenceHint"]:
            digital_gap_score += 18
            explanation.append("Lead appears to rely on social presence only.")
        if features["hasBookingLink"]:
            digital_gap_score -= 10
            explanation.append("Booking flow detected.")
        digital_gap_score = max(0, min(digital_gap_score, 100))

        fit_score = lead.fitScore or 50
        if (lead.businessType or "").lower() in {"restaurant", "bar", "bistro", "cafe", "cafeteria"}:
            fit_score = max(fit_score, 72)
            explanation.append("Business type matches FUDI restaurant focus.")
        if features["hasMenuLink"]:
            fit_score = min(100, fit_score + 8)
            explanation.append("Menu signal detected.")

        contactability_score = int(features["contactabilityScore"])
        explanation.extend(features["contactabilityReasons"])
        priority_score = round(
            newness_score * 0.22
            + digital_gap_score * 0.33
            + fit_score * 0.27
            + contactability_score * 0.18
        )
        confidence = round((contactability_score + fit_score + min(features["textLength"] // 20, 100)) / 3)
        return (
            ScoreBreakdown(
                newnessScore=newness_score,
                digitalGapScore=digital_gap_score,
                fitScore=fit_score,
                contactabilityScore=contactability_score,
                priorityScore=priority_score,
                explanation=list(dict.fromkeys(explanation)) or ["Score recomputed from enrichment signals."],
            ),
            max(0, min(confidence, 100)),
        )


def get_enrichment_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> EnrichmentService:
    return EnrichmentService(database)
