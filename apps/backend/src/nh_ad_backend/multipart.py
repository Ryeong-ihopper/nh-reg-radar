"""Bounded multipart/form-data parser without an optional framework dependency."""

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from io import BytesIO

from fastapi import Request

from nh_ad_backend.storage import MAX_FILE_SIZE


MAX_FILES = 13
MAX_MULTIPART_SIZE = MAX_FILES * MAX_FILE_SIZE + 1024 * 1024


class MultipartError(ValueError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True)
class ParsedFile:
    file_name: str
    content_type: str | None
    stream: BytesIO


@dataclass(frozen=True)
class MultipartForm:
    fields: dict[str, str]
    files: dict[str, list[ParsedFile]]


async def parse_multipart(request: Request) -> MultipartForm:
    content_type = request.headers.get("content-type", "")
    if (
        not content_type.casefold().startswith("multipart/form-data")
        or "boundary=" not in content_type
    ):
        raise MultipartError(415, "FILE_NOT_SUPPORTED", "multipart/form-data 요청이 필요합니다.")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            parsed_length = int(content_length)
        except ValueError as exc:
            raise MultipartError(400, "BAD_REQUEST", "Content-Length 값을 확인해 주세요.") from exc
        if parsed_length < 0:
            raise MultipartError(400, "BAD_REQUEST", "Content-Length 값을 확인해 주세요.")
        if parsed_length > MAX_MULTIPART_SIZE:
            raise MultipartError(413, "FILE_SIZE_EXCEEDED", "요청 파일 용량이 제한을 초과했습니다.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_MULTIPART_SIZE:
            raise MultipartError(413, "FILE_SIZE_EXCEEDED", "요청 파일 용량이 제한을 초과했습니다.")
    envelope = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    message = BytesParser(policy=policy.default).parsebytes(envelope)
    if not message.is_multipart():
        raise MultipartError(400, "BAD_REQUEST", "multipart 요청 경계를 확인해 주세요.")
    fields: dict[str, str] = {}
    files: dict[str, list[ParsedFile]] = {}
    file_count = 0
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        name = part.get_param("name", header="content-disposition")
        if not isinstance(name, str) or not name:
            continue
        payload = part.get_payload(decode=True) or b""
        if not isinstance(payload, bytes):
            raise MultipartError(400, "BAD_REQUEST", f"{name} 값을 읽을 수 없습니다.")
        file_name = part.get_filename()
        if file_name is None:
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset)
            except (LookupError, UnicodeDecodeError) as exc:
                raise MultipartError(400, "BAD_REQUEST", f"{name} 값을 읽을 수 없습니다.") from exc
            if name in fields:
                raise MultipartError(400, "BAD_REQUEST", f"{name} 값이 중복되었습니다.")
            if len(payload) > 4096:
                raise MultipartError(400, "BAD_REQUEST", f"{name} 값이 너무 깁니다.")
            fields[name] = decoded
            continue
        file_count += 1
        if file_count > MAX_FILES or len(payload) > MAX_FILE_SIZE:
            raise MultipartError(
                413, "FILE_SIZE_EXCEEDED", "파일 용량 또는 개수 제한을 초과했습니다."
            )
        files.setdefault(name, []).append(
            ParsedFile(
                file_name=file_name, content_type=part.get_content_type(), stream=BytesIO(payload)
            )
        )
    allowed_fields = {
        "advertisementName",
        "productGroup",
        "advertisementType",
        "channelType",
        "departmentId",
        "memo",
    }
    allowed_files = {"advertisementFile", "productDescriptionFile", "termsFile", "additionalFiles"}
    if set(fields) - allowed_fields or set(files) - allowed_files:
        raise MultipartError(400, "BAD_REQUEST", "지원하지 않는 multipart 필드가 포함되었습니다.")
    for name in ("advertisementFile", "productDescriptionFile", "termsFile"):
        if len(files.get(name, [])) > 1:
            raise MultipartError(400, "BAD_REQUEST", f"{name} 파일은 하나만 첨부할 수 있습니다.")
    if len(files.get("additionalFiles", [])) > 10:
        raise MultipartError(400, "BAD_REQUEST", "additionalFiles는 최대 10개입니다.")
    return MultipartForm(fields=fields, files=files)
