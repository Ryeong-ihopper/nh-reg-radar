"""Connect operational runs to the original NH frontend/backend.

Loopback-only viewer; the local execution config enables the real review queue by default.
Original prediction files remain the source of truth across server restarts.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import secrets
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from threading import Lock


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "apps/backend/src"),
    str(ROOT / "packages/ai-providers/src"),
    str(ROOT / "packages/parser-contracts/src"),
    str(ROOT / "rag-pipeline"),
    str(ROOT / "rag-pipeline/tools"),
    str(ROOT / "scripts"),
]

import pypdfium2 as pdfium  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: E402
from starlette.exceptions import HTTPException  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from nh_ad_backend.domain import Advertisement, AdvertisementFile, User  # noqa: E402
from nh_ad_backend.main import build_services, create_app  # noqa: E402
from nh_ad_backend.pdf_preview import PdfPreview, PdfPreviewMetadata  # noqa: E402
from nh_ad_backend.results import ResultAnnotation, ResultEvidence, ResultItem  # noqa: E402
from nh_ad_backend.reviews import Review, ReviewBundle, ReviewJob  # noqa: E402
from nh_ad_backend.security import hash_password  # noqa: E402
from nh_ad_backend.settings import Settings  # noqa: E402

from local_hwp_preview import LocalHwpPreview  # noqa: E402
from operational_server_config import load_server_config  # noqa: E402
from operational_locations import project_reading_citations, resolve_locations  # noqa: E402

LOCAL_VIEWER_LOGIN = "admin"
LOCAL_VIEWER_PASSWORD = "admin"


VERDICTS = {
    "COMPLIANT": ("충족", "APPROPRIATE", "LOW"),
    "NOT_APPLICABLE": ("미해당", "APPROPRIATE", "LOW"),
    "VIOLATION": ("위반", "NEEDS_REVISION", "HIGH"),
    "UNDETERMINED": ("판단불가", "NEEDS_CONFIRMATION", "CHECK_REQUIRED"),
}


def _routing_value(routing, field):
    value = (routing or {}).get(field)
    if isinstance(value, dict):
        value = value.get("value")
    return value if isinstance(value, str) else ""


class LocalPdfPreview:
    """Render the supplied original PDF at the input contract's 200 DPI."""

    def __init__(self):
        self.lock = Lock()
        self.cache = {}

    def describe(self, *, body, **_):
        with self.lock, pdfium.PdfDocument(body) as pdf:
            return PdfPreviewMetadata(len(pdf))

    def render(self, *, body, page_no, **_):
        key = (hashlib.sha256(body).hexdigest(), page_no)
        with self.lock:
            if key not in self.cache:
                with pdfium.PdfDocument(body) as pdf:
                    page = pdf[page_no - 1]
                    bitmap = page.render(scale=200 / 72)
                    output = io.BytesIO()
                    bitmap.to_pil().save(output, format="PNG")
                    self.cache[key] = PdfPreview(output.getvalue(), len(pdf))
                    bitmap.close()
                    page.close()
            return self.cache[key]


class SpaFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code == 404 and "." not in path.rsplit("/", 1)[-1]:
                return await super().get_response("index.html", scope)
            raise



def project_results(
    services,
    integrated,
    candidates,
    rules,
    evidence,
    review_id,
    file_id,
    digest,
    model="gemma-4-26b-NVFP4-MTP",
    *,
    product_id=None,
    product_name=None,
):
    for candidate in candidates:
        judgment = project_reading_citations(candidate["judgment"])
        if judgment.get("applicability") == "NOT_APPLICABLE" or judgment.get("verdict") == "NOT_APPLICABLE":
            continue
        item_id = candidate["item_id"]
        rule = rules[item_id]
        label, status, risk = VERDICTS[judgment["verdict"]]
        scope_key = hashlib.sha256(str(product_id or "shared").encode("utf-8")).hexdigest()[:8]
        item_key = f"ITEM-{digest}-{scope_key}-{item_id}"
        category = rule.get("category")
        review_type = {"PRESENCE": "REQUIRED_PHRASE", "PROHIBIT": "MISLEADING_EXPRESSION"}.get(category, "PRODUCT_CONSISTENCY")
        cited = [evidence[eid] for eid in judgment.get("evidence_ids", []) if eid in evidence]
        scope_label = f"[{product_name}] " if product_name else ""
        target = f"{scope_label}[{item_id}] {rule['title']} · {label}"
        if cited:
            target += "\n" + cited[0]["text"][:180]
        reason = f"모델 판정: {label}. " + judgment["reason"]
        reason += "\n" + "\n".join(f"• {check['requirement']}: {check['status']} — {check['reason']}" for check in judgment.get("requirement_checks", []))
        if cited:
            reason += "\n광고 인용문:\n" + "\n\n".join(doc["text"] for doc in cited)
        annotation = None
        locations = resolve_locations(integrated, judgment, evidence)
        if locations:
            # The result API has one coordinate slot.  Do not union disjoint
            # cited lines into a page-sized rectangle; use the most focused
            # exact location and leave all locations available in the
            # operational workspace.
            first = min(locations, key=lambda loc: (
                loc["precision"] != "LINE",
                (loc["bbox"][2] - loc["bbox"][0]) * (loc["bbox"][3] - loc["bbox"][1]),
                loc["pageNo"], loc["bbox"][1], loc["bbox"][0],
            ))
            x, y = first["bbox"][0], first["bbox"][1]
            w, h = first["bbox"][2] - x, first["bbox"][3] - y
            cw, ch = first["width"], first["height"]
            approximate = first["precision"] == "REGION"
            coordinate = dict(sourceWidth=cw, sourceHeight=ch, sourceUnit="px", x=x, y=y, width=w, height=h,
                              normalizedX=x/cw, normalizedY=y/ch, normalizedWidth=w/cw, normalizedHeight=h/ch,
                              rotation=0, coordinateConfidence=None)
            annotation = ResultAnnotation(f"ANN-{digest}-{scope_key}-{item_id}", item_key, first["asset_id"] or file_id, "ADVERTISEMENT",
                review_type, risk, target, "BOX", "LOCATED", None,
                "parser-region-ref-v1" if approximate else "parser-line-ref-v1", "NORMALIZED_COORDINATE",
                first["source_page_no"], coordinate, matched_text=None if approximate else (cited[0]["text"] if cited else None))
        # A direct source link is not a measured retrieval score. Template items are
        # independent review criteria and must not be mislabeled as regulation-v2 rows.
        is_template = rule.get("source_sheet") == "HWPX_TEMPLATE" or item_id.startswith("TPL-")
        source_version = "STDVER-TEMPLATE" if is_template else "STDVER-V2"
        source_name = "내부 광고 심의 템플릿" if is_template else "규제목록 v2"
        criterion = (
            rule.get("criterion")
            or rule.get("guide")
            or rule.get("question")
            or rule["title"]
        )
        linked_rule = ResultEvidence(f"EVD-{scope_key}-{item_id}", None, source_version, "GUIDELINE",
            f"{source_name} · {item_id} · {rule['title']} (직접 연결·검색 점수 미제공)", None,
            criterion, 1, 0.0, "RULE_METADATA")
        detail = {
            "rule": {"matched": False, "ruleIds": [item_id], "severity": risk,
                     "productId": product_id, "productName": product_name},
            "rag": {"topRelevanceScore": None, "evidenceCount": 1, "evidenceSufficient": True, "status": "CONNECTED", "failureCode": None},
            "llm": {"schemaVersion": "review-structured-output-v1", "status": "VALID", "decision": judgment["verdict"], "confidence": None},
            "parser": {"confidenceStatus": "READABLE"},
            "final": {"riskLevel": risk, "decisionRule": "LLM_OPERATIONAL_RESULT"},
        }
        services.results.repository.add(ResultItem(item_key, review_id, review_type, target, status, risk,
            "operational-display-v1", (), detail, "CONNECTED", None, reason, None, "LLM",
            model, annotation.page_no if annotation else None, (linked_rule,), annotation))


def build_operational_server(args):
    """Start the real registration → queue → pipeline path with no seed result."""
    args.state_dir.mkdir(parents=True, exist_ok=True)
    server = load_server_config(args.server_config) if getattr(args, "server_config", None) else None
    settings = Settings(
        app_env="test",
        refresh_cookie_secure=bool(server),
        jwt_secret=server.jwt_secret if server else None,
        cors_allowed_origins=server.public_url if server else f"http://localhost:{args.port},http://127.0.0.1:{args.port}",
        private_storage_path=args.state_dir / "private",
    )
    services = build_services(settings)
    # This loopback-only PoC viewer deliberately uses one fixed local account.
    # Separate registrations support development comparisons; IDs and storage
    # objects remain independent. Server deployment retains duplicate checks.
    if server is None:
        services.repository.allow_duplicate_advertisement_files = True
    # It is not a production authentication configuration.
    login_id = server.login_id if server else LOCAL_VIEWER_LOGIN
    password = server.password if server else LOCAL_VIEWER_PASSWORD
    user = User(
        "local-operator", "광고 심의 담당자", login_id, hash_password(password),
        "DPT-LOCAL", "로컬 검토", ("PRODUCT_DEPARTMENT_USER", "COMPLIANCE_REVIEWER"),
    )
    services.repository.users[user.user_id] = user
    services = replace(services, pdf_preview=LocalPdfPreview(), hwp_preview=LocalHwpPreview())
    from operational_web_bridge import ExecutionBridge
    bridge = ExecutionBridge(services, args.state_dir, args.execution_config, project_results)
    backend = create_app(settings, services)
    bridge.install(backend)
    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            bridge.pause_for_shutdown()

    app = FastAPI(docs_url=None, redoc_url=None, lifespan=lifespan)
    entry_token = secrets.token_urlsafe(32)

    @app.get("/open/{token}")
    async def open_local(token: str):
        nonlocal entry_token
        if server or not entry_token or not secrets.compare_digest(token, entry_token):
            return JSONResponse({"message": "사용된 로컬 연결입니다. 로그인 화면을 이용하세요."}, status_code=404)
        entry_token = ""
        _, refresh, _ = services.auth.login(user.email, password, "127.0.0.1", "operational-web", "local-open")
        response = RedirectResponse("/advertisements")
        response.set_cookie("refreshToken", refresh, httponly=True, secure=False, samesite="lax", path="/api/v1/auth")
        return response

    @app.post("/api/v1/auth/login")
    async def local_login(request: Request):
        try:
            payload = await request.json()
            access, refresh, authenticated = services.auth.login(
                str(payload.get("email", "")), str(payload.get("password", "")),
                request.client.host if request.client else "127.0.0.1", request.headers.get("user-agent", ""), "local-operational-login",
            )
        except (ValueError, TypeError) as exc:
            return JSONResponse({"code": getattr(exc, "code", "UNAUTHORIZED"), "message": getattr(exc, "message", "로그인에 실패했습니다.")}, status_code=getattr(exc, "status_code", 401))
        response = JSONResponse({"accessToken": access, "tokenType": "Bearer", "expiresIn": 1800, "user": {"userId": authenticated.user_id, "userName": authenticated.user_name, "departmentId": authenticated.department_id, "departmentName": authenticated.department_name, "roles": list(authenticated.roles)}})
        response.set_cookie("refreshToken", refresh, httponly=True, secure=bool(server), samesite="lax", path="/api/v1/auth")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/auth/local-session")
    async def local_session(request: Request):
        """Issue a fresh loopback viewer session without exposing credentials.

        The deployed server keeps its normal login flow.  On localhost the UI
        can recover from access-token expiry without dropping the reviewer on
        a login screen while a long RAG run is being inspected.
        """
        if server is not None or not request.client or request.client.host not in {
            "127.0.0.1", "::1", "localhost",
        }:
            return JSONResponse({"code": "NOT_FOUND", "message": "요청한 대상을 찾을 수 없습니다."}, status_code=404)
        access, _, authenticated = services.auth.login(
            user.email, password, request.client.host, request.headers.get("user-agent", ""),
            "local-operational-session",
        )
        response = JSONResponse({
            "accessToken": access,
            "tokenType": "Bearer",
            "expiresIn": 1800,
            "user": {
                "userId": authenticated.user_id,
                "userName": authenticated.user_name,
                "departmentId": authenticated.department_id,
                "departmentName": authenticated.department_name,
                "roles": list(authenticated.roles),
            },
        })
        response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/api/v1", backend)
    app.mount("/", SpaFiles(directory=args.static_dir, html=True))
    manifest = ({"url": f"{server.public_url}/advertisements", "mode": "server_operational_registration"}
                if server else {"url": f"http://localhost:{args.port}/advertisements", "open_url": f"http://localhost:{args.port}/open/{entry_token}", "email": user.email, "password": password, "mode": "operational_registration"})
    (args.state_dir / "viewer-session.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return app


def build_viewer(args):
    if args.result is None:
        return build_operational_server(args)
    output = json.loads(args.result.read_text(encoding="utf-8"))
    integrated = json.loads(args.integrated.read_text(encoding="utf-8"))
    ad_id = integrated["document"]["ad_id"]
    ad_results = [ad for ad in output["ads"] if ad["ad_id"] == ad_id]
    if not ad_results:
        raise ValueError("Result does not contain the integrated advertisement")
    requests = [json.loads(line) for line in args.requests.read_text(encoding="utf-8").splitlines() if line.strip()]
    candidates = [candidate for ad in ad_results for candidate in ad["candidates"]]
    if any(row["status"] != "predicted" or not row.get("judgment") for row in candidates):
        raise ValueError("The viewer requires completed predictions; no failure is converted to a verdict")
    digest = hashlib.sha256(args.result.read_bytes()).hexdigest()[:12]
    advertisement_id, review_id, file_id = f"ADV-{digest}", f"REV-{digest}", f"FILE-{digest}"
    completed = datetime.fromisoformat(output["assembled_at"])
    original = args.original.read_bytes()
    if args.original.name != integrated["document"]["source_file"]:
        raise ValueError("Original filename must match the integrated parser input")
    args.state_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(app_env="test", refresh_cookie_secure=False,
                        cors_allowed_origins=f"http://localhost:{args.port},http://127.0.0.1:{args.port}",
                        private_storage_path=args.state_dir / "private")
    services = build_services(settings)
    login_id = LOCAL_VIEWER_LOGIN
    password = LOCAL_VIEWER_PASSWORD
    user = User("local-reviewer", "실행 결과 검토", login_id, hash_password(password),
                "DPT-LOCAL", "로컬 검토", ("COMPLIANCE_REVIEWER",))
    services.repository.users[user.user_id] = user
    key = services.advertisements.storage.put(original)
    source_file = AdvertisementFile(file_id, "ADVERTISEMENT", args.original.name, key,
                                    "application/pdf", len(original), hashlib.sha256(original).hexdigest())
    metadata = integrated["document"].get("routing_metadata", {})
    product = _routing_value(metadata, "product_group")
    result_routing = ad_results[0].get("routing") or {}
    template = (
        _routing_value(metadata, "template_id")
        or _routing_value(result_routing, "product_subtype")
        or _routing_value(result_routing, "template_id")
    )
    product_group = (
        "LOAN" if product == "대출성"
        else "INVESTMENT" if product == "투자성"
        else "SAVINGS" if "적립식" in template
        else "DEPOSIT"
    )
    services.repository.add_advertisement(Advertisement(
        advertisement_id, args.original.stem, product_group, "NOTICE", None,
        user.department_id, user.user_id, "REVIEW_COMPLETED",
        "저장된 Gemma 실제 판정 결과. 미해당은 적정 그룹에 포함되며 각 항목에 원판정을 표시합니다. 광고유형 NOTICE는 화면 호환값입니다.",
        completed, files=[source_file], latest_review_id=review_id))
    standard_versions = ["STDVER-V2"]
    if any(str(candidate.get("item_id", "")).startswith("TPL-") for candidate in candidates):
        standard_versions.insert(0, "STDVER-TEMPLATE")
    review = Review(review_id, advertisement_id, None, 1, "REVIEW_COMPLETED", date(2026, 9, 6),
                    tuple(standard_versions), ("REQUIRED_PHRASE", "MISLEADING_EXPRESSION", "PRODUCT_CONSISTENCY"),
                    False, False, "실제 운영형 실행결과 조회", completed, user.user_id, completed)
    job = ReviewJob(f"JOB-{digest}", review_id, "INITIAL_REVIEW", "COMPLETED", 100, 0, 0,
                    completed, is_retryable=False, updated_at=completed)
    services.reviews.repository.add(ReviewBundle(review, job, []))
    for ad_result in ad_results:
        scope_id = ad_result.get("scope_id") or ad_result["ad_id"]
        payloads = [
            json.loads(row["messages"][1]["content"])
            for row in requests
            if row["ad_id"] == scope_id
        ]
        rules = {rule["item_id"]: rule for payload in payloads for rule in payload["rules"]}
        evidence = {doc["evidence_id"]: doc for payload in payloads for doc in payload["documents"]}
        project_results(
            services,
            integrated,
            ad_result["candidates"],
            rules,
            evidence,
            review_id,
            file_id,
            digest,
            product_id=ad_result.get("product_id"),
            product_name=ad_result.get("product_name"),
        )
    services = replace(
        services,
        pdf_preview=LocalPdfPreview(),
        hwp_preview=LocalHwpPreview(),
    )
    backend = create_app(settings, services)

    bridge = None
    if getattr(args, "execution_config", None):
        from operational_web_bridge import ExecutionBridge
        bridge = ExecutionBridge(services, args.state_dir, args.execution_config, project_results)
        bridge.install(backend)

    if getattr(args, "reference_workbook", None):
        from researcher_demo_reference import load_reference, reference_for_ad
        corrections = {}
        for correction in args.reference_correction:
            number, verdict = correction.split("=", 1)
            corrections[int(number)] = verdict
        extras = json.loads(args.reference_extra.read_text(encoding="utf-8")) if args.reference_extra else []
        reference = load_reference(args.reference_workbook, corrections, extras)

        @backend.get("/operational/reference/{advertisement_id}")
        async def researcher_reference(advertisement_id: str, request: Request):
            actor = services.auth.authenticate(request.headers.get("authorization", "").removeprefix("Bearer "))
            ad = services.advertisements.get(actor, advertisement_id, "researcher-reference")
            return reference_for_ad(reference, ad)

    @backend.middleware("http")
    async def read_only(request: Request, call_next):
        if not bridge and request.method not in {"GET", "HEAD", "OPTIONS"} and "/auth/" not in request.url.path:
            return JSONResponse({"code": "READ_ONLY_REVIEW", "message": "현재는 완료된 실제 판정 결과 확인용입니다. 신규 심의 실행은 아직 이 화면에 연결되지 않았습니다."}, status_code=409)
        return await call_next(request)

    app = FastAPI(docs_url=None, redoc_url=None)
    if bridge:
        app.add_event_handler("shutdown", bridge.pause_for_shutdown)
    entry_token = secrets.token_urlsafe(32)
    latest_id = services.repository.get_advertisement(advertisement_id).latest_review_id or review_id
    latest_bundle = services.reviews.repository.get(latest_id)
    landing = f"/reviews/{latest_id}/{'results' if latest_bundle.job.status == 'COMPLETED' else 'status'}"

    @app.get("/open/{token}")
    async def open_local(token: str):
        nonlocal entry_token
        if not entry_token or not secrets.compare_digest(token, entry_token):
            return JSONResponse({"message": "사용된 로컬 연결입니다. 로그인 화면을 이용하세요."}, status_code=404)
        entry_token = ""
        _, refresh, _ = services.auth.login(user.email, password, "127.0.0.1", "local-viewer", "local-open")
        response = RedirectResponse(landing)
        response.set_cookie("refreshToken", refresh, httponly=True, secure=False, samesite="lax", path="/api/v1/auth")
        return response

    @app.post("/api/v1/auth/login")
    async def local_login(request: Request):
        """Loopback demo login; intentionally outside the production OpenAPI contract."""
        try:
            payload = await request.json()
            access, refresh, authenticated = services.auth.login(
                str(payload.get("email", "")),
                str(payload.get("password", "")),
                request.client.host if request.client else "127.0.0.1",
                request.headers.get("user-agent", ""),
                "local-demo-login",
            )
        except (ValueError, TypeError) as exc:
            status = getattr(exc, "status_code", 401)
            code = getattr(exc, "code", "UNAUTHORIZED")
            message = getattr(exc, "message", "이메일 또는 비밀번호가 올바르지 않거나 로그인이 제한되었습니다.")
            return JSONResponse({"code": code, "message": message}, status_code=status)
        response = JSONResponse({
            "accessToken": access,
            "tokenType": "Bearer",
            "expiresIn": 1800,
            "user": {
                "userId": authenticated.user_id,
                "userName": authenticated.user_name,
                "departmentId": authenticated.department_id,
                "departmentName": authenticated.department_name,
                "roles": list(authenticated.roles),
            },
        })
        response.set_cookie("refreshToken", refresh, httponly=True, secure=False, samesite="lax", path="/api/v1/auth")
        response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/api/v1", backend)
    app.mount("/", SpaFiles(directory=args.static_dir, html=True))
    manifest = {"url": f"http://localhost:{args.port}{landing}", "open_url": f"http://localhost:{args.port}/open/{entry_token}",
                "email": user.email, "password": password, "review_id": latest_id,
                "advertisement_id": advertisement_id, "result": str(args.result.resolve()),
                "result_sha256": hashlib.sha256(args.result.read_bytes()).hexdigest(), "items": len(candidates),
                "mode": "automatic_operational_review" if bridge else "read_only_saved_operational_results"}
    (args.state_dir / "viewer-session.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for flag in ("result", "requests", "integrated", "original"):
        parser.add_argument(f"--{flag}", type=Path)
    for flag in ("static-dir", "state-dir"):
        parser.add_argument(f"--{flag}", type=Path, required=True)
    parser.add_argument(
        "--execution-config",
        type=Path,
        default=ROOT / "temp" / "operational-config.local.json",
        help=(
            "Operational parser/search/model config. Defaults to "
            "temp/operational-config.local.json."
        ),
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Disable new operational execution and show only the supplied saved result.",
    )
    parser.add_argument("--port", type=int, default=5180)
    parser.add_argument("--server-config", type=Path, help="Explicit HTTPS/login secrets for server execution")
    args = parser.parse_args()
    supplied_seed = [args.result, args.requests, args.integrated, args.original]
    if any(supplied_seed) and not all(supplied_seed):
        parser.error("saved-result mode requires --result, --requests, --integrated, and --original together")
    if args.server_config and any(supplied_seed):
        parser.error("server mode restores its persistent state; saved-result seed mode is local only")
    if args.read_only:
        if args.result is None:
            parser.error("--read-only requires a saved result input")
        args.execution_config = None
    elif not args.execution_config.is_file():
        parser.error(
            "operational execution config was not found: "
            f"{args.execution_config}. Provide --execution-config or use --read-only."
        )
    server = load_server_config(args.server_config) if args.server_config else None
    uvicorn.run(build_viewer(args), host=server.bind_host if server else "127.0.0.1", port=args.port,
                ssl_certfile=server.tls_cert_file if server else None,
                ssl_keyfile=server.tls_key_file if server else None)
