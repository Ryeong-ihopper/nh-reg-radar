"""Private object-storage boundary and upload validation for M2."""

import hashlib
import os
import re
import secrets
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import BinaryIO, Protocol


MAX_FILE_SIZE = 50 * 1024 * 1024
ALLOWED_MIME_TYPES: dict[str, frozenset[str]] = {
    "jpg": frozenset({"image/jpeg"}),
    "jpeg": frozenset({"image/jpeg"}),
    "png": frozenset({"image/png"}),
    "pdf": frozenset({"application/pdf"}),
    "hwp": frozenset({"application/x-hwp", "application/haansofthwp", "application/octet-stream"}),
    "hwpx": frozenset(
        {
            "application/vnd.hancom.hwpx",
            "application/zip",
            "application/octet-stream",
        }
    ),
}


class UploadValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedUpload:
    original_file_name: str
    mime_type: str
    size: int
    checksum: str
    body: bytes


class ObjectStorage(Protocol):
    def put(self, body: bytes) -> str: ...

    def open(self, storage_key: str) -> BinaryIO: ...

    def delete(self, storage_key: str) -> None: ...


def normalize_file_name(file_name: str) -> str:
    normalized = PurePath(file_name.replace("\\", "/")).name
    normalized = re.sub(r"[\x00-\x1f\x7f]", "", normalized).strip()
    if not normalized or normalized in {".", ".."}:
        raise UploadValidationError("FILE_NOT_SUPPORTED", "파일 이름을 확인해 주세요.")
    return normalized[:500]


def validate_upload(file_name: str, mime_type: str | None, stream: BinaryIO) -> ValidatedUpload:
    normalized_name = normalize_file_name(file_name)
    extension = Path(normalized_name).suffix.casefold().lstrip(".")
    if extension not in ALLOWED_MIME_TYPES:
        raise UploadValidationError("FILE_NOT_SUPPORTED", "지원하지 않는 파일 형식입니다.")
    normalized_mime = (mime_type or "application/octet-stream").casefold().split(";", 1)[0]
    if normalized_mime not in ALLOWED_MIME_TYPES[extension]:
        raise UploadValidationError(
            "FILE_NOT_SUPPORTED", "파일 형식과 MIME 형식이 일치하지 않습니다."
        )

    chunks: list[bytes] = []
    size = 0
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        if size > MAX_FILE_SIZE:
            raise UploadValidationError("FILE_SIZE_EXCEEDED", "파일 용량이 50MB를 초과했습니다.")
        chunks.append(chunk)
        digest.update(chunk)
    body = b"".join(chunks)
    if not body or not _has_valid_signature(extension, body):
        raise UploadValidationError(
            "FILE_READ_FAILED", "파일을 읽지 못했습니다. 파일을 다시 확인해 주세요."
        )
    return ValidatedUpload(
        original_file_name=normalized_name,
        mime_type=normalized_mime,
        size=size,
        checksum=digest.hexdigest(),
        body=body,
    )


def _has_valid_signature(extension: str, body: bytes) -> bool:
    if extension in {"jpg", "jpeg"}:
        return body.startswith(b"\xff\xd8\xff") and body.endswith(b"\xff\xd9")
    if extension == "png":
        return _valid_png(body)
    if extension == "pdf":
        return body.startswith(b"%PDF-") and b"%%EOF" in body[-1024:]
    if extension == "hwp":
        return body.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if extension == "hwpx":
        try:
            from io import BytesIO

            with zipfile.ZipFile(BytesIO(body)) as archive:
                names = set(archive.namelist())
                return "mimetype" in names or "Contents/content.hpf" in names
        except zipfile.BadZipFile:
            return False
    return False


def _valid_png(body: bytes) -> bool:
    if not body.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    position = 8
    first_chunk = True
    saw_iend = False
    while position + 12 <= len(body):
        length = int.from_bytes(body[position : position + 4], "big")
        chunk_type = body[position + 4 : position + 8]
        end = position + 12 + length
        if end > len(body):
            return False
        data = body[position + 8 : position + 8 + length]
        expected_crc = int.from_bytes(body[position + 8 + length : end], "big")
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
            return False
        if first_chunk and (chunk_type != b"IHDR" or length != 13):
            return False
        first_chunk = False
        position = end
        if chunk_type == b"IEND":
            saw_iend = length == 0
            break
    return saw_iend and position == len(body)


class PrivateFileStorage:
    """Filesystem adapter that never derives paths from user-controlled names."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._root, 0o700)

    def put(self, body: bytes) -> str:
        storage_key = secrets.token_hex(24)
        path = self._path(storage_key)
        with path.open("xb") as destination:
            destination.write(body)
        os.chmod(path, 0o600)
        return storage_key

    def open(self, storage_key: str) -> BinaryIO:
        return self._path(storage_key).open("rb")

    def delete(self, storage_key: str) -> None:
        self._path(storage_key).unlink(missing_ok=True)

    def _path(self, storage_key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{48}", storage_key):
            raise FileNotFoundError("invalid storage identifier")
        path = (self._root / storage_key).resolve()
        if path.parent != self._root:
            raise FileNotFoundError("invalid storage identifier")
        return path
