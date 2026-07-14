"""Focused behavioral tests for deterministic M6 support endpoints."""

from dataclasses import replace

from fastapi.testclient import TestClient

from conftest import JWT_SECRET, login
from nh_ad_backend.api import ApplicationServices
from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.main import create_app
from nh_ad_backend.repository import InMemoryRepository
from nh_ad_backend.settings import Settings
from nh_ad_backend.support import SupportService


def actor(*roles: str) -> CurrentUser:
    return CurrentUser("reviewer", "준법담당", "DPT-C", "준법부", roles, 1)


def test_support_service_retains_histories_snapshots_and_download_audit(
    repository: InMemoryRepository,
) -> None:
    service = SupportService(audit_sink=repository.add_audit_event)

    first = service.decide(actor("COMPLIANCE_REVIEWER"), "SUG-0001", {"decisionStatus": "ACCEPTED"})
    second = service.decide(
        actor("COMPLIANCE_REVIEWER"),
        "SUG-0001",
        {"decisionStatus": "MODIFIED_AND_USED", "finalText": "조건에 따라 혜택을 제공합니다."},
    )
    assert first["finalText"] != second["finalText"]
    assert len(service.decisions) == 2

    answer = service.question(actor("COMPLIANCE_REVIEWER"), {"question": "확정 표현인가요?"})
    assert answer["needsHumanReview"] is True
    assert service.questions[0]["standardVersionIds"] == []
    assert service.list_questions(actor("COMPLIANCE_REVIEWER")) == [answer]

    draft = service.create_draft("REV-0001", {"includeReviewItemIds": ["ITEM-0001"]})
    service.update_draft(draft["draftId"], {"finalContent": "수정된 심의 의견"})
    assert len(service.drafts[draft["draftId"]]["editHistory"]) == 2

    hwpx = service.create_report("REV-0001", {"format": "HWPX"})
    pdf = service.create_report("REV-0001", {"format": "PDF"})
    assert pdf["sourceReportId"] == "RPT-0002"
    assert hwpx["snapshotHash"].startswith("sha256:")
    payload, report_format = service.download_report(actor("COMPLIANCE_REVIEWER"), hwpx["reportId"])
    assert report_format == "HWPX"
    assert payload
    assert repository.list_audit_events()[0].action_type == "REPORT_DOWNLOADED"

    comparison = service.create_comparison(
        "ADV-0001", {"baseReviewId": "REV-0001", "revisionId": "REV-0002"}
    )
    assert [item["resolutionStatus"] for item in comparison["items"]] == [
        "RESOLVED",
        "UNRESOLVED",
        "NEW_ISSUE",
    ]
    assert comparison["items"][1]["reanalysisReviewId"]


def test_m6_support_routes_cover_all_mutating_and_lookup_flows(
    services: ApplicationServices, repository: InMemoryRepository
) -> None:
    app = create_app(
        Settings(
            app_env="test",
            jwt_secret=JWT_SECRET,
            cors_allowed_origins="http://localhost:5173",
            refresh_cookie_secure=False,
        ),
        replace(services, support=SupportService(audit_sink=repository.add_audit_event)),
    )
    with TestClient(app) as client:
        product_token, _ = login(client)
        product_headers = {"Authorization": f"Bearer {product_token}"}
        reviewer_token, _ = login(client, "review@example.com")
        reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}

        invalid = client.patch(
            "/api/v1/suggestions/SUG-0001/decision",
            headers=product_headers,
            json={"decisionStatus": "MODIFIED_AND_USED"},
        )
        assert invalid.status_code == 400
        assert (
            client.patch(
                "/api/v1/suggestions/SUG-0001/decision",
                headers=product_headers,
                json={"decisionStatus": "ACCEPTED"},
            ).status_code
            == 200
        )
        assert (
            client.get("/api/v1/reviews/REV-0001/suggestions", headers=product_headers).status_code
            == 200
        )

        qa = client.post(
            "/api/v1/qa/questions", headers=product_headers, json={"question": "검토?"}
        )
        assert qa.status_code == 200
        assert qa.json()["needsHumanReview"] is True
        assert (
            client.get("/api/v1/qa/questions", headers=product_headers).json()[0]["qaId"]
            == qa.json()["qaId"]
        )

        draft = client.post(
            "/api/v1/reviews/REV-0001/opinion-drafts", headers=product_headers, json={}
        ).json()
        assert (
            client.patch(
                f"/api/v1/opinion-drafts/{draft['draftId']}",
                headers=product_headers,
                json={"finalContent": "검토 의견"},
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/v1/reviews/REV-0001/opinion-drafts", headers=product_headers
            ).status_code
            == 200
        )

        report = client.post(
            "/api/v1/reviews/REV-0001/reports", headers=product_headers, json={"format": "PDF"}
        ).json()
        assert report["sourceReportId"]
        assert (
            client.get(f"/api/v1/reports/{report['reportId']}", headers=product_headers).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/v1/reports/{report['reportId']}/download", headers=product_headers
            ).status_code
            == 403
        )
        download = client.get(
            f"/api/v1/reports/{report['reportId']}/download", headers=reviewer_headers
        )
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/octet-stream"

        comparison = client.post(
            "/api/v1/advertisements/ADV-0001/comparisons",
            headers=product_headers,
            json={"baseReviewId": "REV-0001", "revisionId": "REV-0002"},
        )
        assert comparison.status_code == 200
        assert (
            client.get(
                f"/api/v1/comparisons/{comparison.json()['comparisonId']}", headers=product_headers
            ).status_code
            == 200
        )
