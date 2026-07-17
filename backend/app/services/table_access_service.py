import base64
import datetime
import hashlib
import hmac
import json
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.services import alipos_api

_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_MANUAL_CODE_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{6}$")
_START_PARAM_RE = re.compile(r"^t_([0-9A-HJKMNP-TV-Z]{6})_([A-Za-z0-9_-]{12})$")
_TABLE_NUMBER_RE = re.compile(r"([0-9]+)\s*$")


class InvalidTableEntry(ValueError):
    pass


class InvalidTableDirectory(RuntimeError):
    pass


def manual_code_from_title(title: str) -> str:
    match = _TABLE_NUMBER_RE.search(title.strip())
    if match is None or len(match.group(1)) > 6:
        raise InvalidTableDirectory(
            f"Table title has no one-to-six digit trailing number: {title!r}"
        )
    return str(int(match.group(1)))


@dataclass(frozen=True)
class TableDirectoryEntry:
    table_id: uuid.UUID
    table_title: str
    hall_id: uuid.UUID
    hall_title: str
    service_percent: Decimal
    manual_code: str


@dataclass(frozen=True)
class TableTokenClaims:
    table_id: uuid.UUID
    expires_at: datetime.datetime


@dataclass(frozen=True)
class TableResolution:
    table_title: str
    hall_title: str
    service_percent: Decimal
    manual_code: str
    access_token: str


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


async def get_table_directory() -> list[TableDirectoryEntry]:
    payload = await alipos_api.get_halls_and_tables()
    if not isinstance(payload, dict):
        raise InvalidTableDirectory("Table directory payload is not an object")
    raw_halls = payload.get("halls")
    raw_tables = payload.get("tables")
    if not isinstance(raw_halls, list) or not isinstance(raw_tables, list):
        raise InvalidTableDirectory("Table directory arrays are missing")

    halls: dict[uuid.UUID, tuple[str, Decimal]] = {}
    for hall in raw_halls:
        try:
            hall_id = uuid.UUID(str(hall["id"]))
            hall_title = str(hall.get("title") or "")
            service_percent = Decimal(str(hall.get("servicePercent") or 0))
            if not service_percent.is_finite():
                raise InvalidTableDirectory("Hall directory entry is invalid")
        except (
            AttributeError,
            InvalidOperation,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise InvalidTableDirectory("Hall directory entry is invalid") from exc
        if hall_id in halls:
            raise InvalidTableDirectory("Duplicate hall identifier")
        halls[hall_id] = (hall_title, service_percent)

    entries: list[TableDirectoryEntry] = []
    table_ids: set[uuid.UUID] = set()
    manual_codes: set[str] = set()
    for table in raw_tables:
        try:
            table_id = uuid.UUID(str(table["id"]))
            hall_id = uuid.UUID(str(table["hallId"]))
            table_title = str(table.get("title") or "")
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise InvalidTableDirectory("Table directory entry is invalid") from exc
        if table_id in table_ids:
            raise InvalidTableDirectory("Duplicate table identifier")
        hall = halls.get(hall_id)
        if hall is None:
            raise InvalidTableDirectory(f"Table has unknown hall: {table_title!r}")
        manual_code = manual_code_from_title(table_title)
        if manual_code in manual_codes:
            raise InvalidTableDirectory(f"Duplicate table number {manual_code}")

        table_ids.add(table_id)
        manual_codes.add(manual_code)
        hall_title, service_percent = hall
        entries.append(
            TableDirectoryEntry(
                table_id=table_id,
                table_title=table_title,
                hall_id=hall_id,
                hall_title=hall_title,
                service_percent=service_percent,
                manual_code=manual_code,
            )
        )
    return entries


class TableAccessService:
    def __init__(
        self,
        secret: str,
        bot_username: str,
        access_ttl_seconds: int = 8 * 60 * 60,
    ) -> None:
        if not secret:
            raise ValueError("Table access secret is required")
        self._secret = secret.encode()
        self._bot_username = bot_username
        self._access_ttl_seconds = access_ttl_seconds

    def _digest(self, purpose: str, value: str) -> bytes:
        message = f"{purpose}:{value}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).digest()

    def build_manual_code(self, table_id: uuid.UUID) -> str:
        number = int.from_bytes(self._digest("manual", table_id.hex)[:4], "big") >> 2
        chars: list[str] = []
        for _ in range(6):
            number, remainder = divmod(number, len(_CROCKFORD_ALPHABET))
            chars.append(_CROCKFORD_ALPHABET[remainder])
        return "".join(reversed(chars))

    def build_start_param(self, table_id: uuid.UUID) -> str:
        code = self.build_manual_code(table_id)
        signature = _b64encode(self._digest("qr", code)[:9])
        return f"t_{code}_{signature}"

    def parse_start_param(self, value: str) -> str:
        match = _START_PARAM_RE.fullmatch(value.strip())
        if match is None:
            raise InvalidTableEntry("Invalid table QR")
        code, received_signature = match.groups()
        expected_signature = _b64encode(self._digest("qr", code)[:9])
        if not hmac.compare_digest(received_signature, expected_signature):
            raise InvalidTableEntry("Invalid table QR")
        return code

    def issue_access_token(
        self,
        entry: TableDirectoryEntry,
        now: datetime.datetime | None = None,
        expires_at: datetime.datetime | None = None,
    ) -> str:
        issued_at = now or datetime.datetime.now(datetime.UTC)
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=datetime.UTC)
        token_expires_at = expires_at or (
            issued_at + datetime.timedelta(seconds=self._access_ttl_seconds)
        )
        if token_expires_at.tzinfo is None:
            token_expires_at = token_expires_at.replace(tzinfo=datetime.UTC)
        if token_expires_at <= issued_at:
            raise InvalidTableEntry("Table access token expired")
        payload = json.dumps(
            {
                "exp": int(token_expires_at.timestamp()),
                "tid": entry.table_id.hex,
                "v": 1,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        encoded_payload = _b64encode(payload)
        signature = _b64encode(self._digest("access", encoded_payload)[:16])
        return f"ta1.{encoded_payload}.{signature}"

    def verify_access_token(
        self,
        token: str,
        now: datetime.datetime | None = None,
    ) -> TableTokenClaims:
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "ta1":
            raise InvalidTableEntry("Invalid table access token")
        encoded_payload, received_signature = parts[1], parts[2]
        expected_signature = _b64encode(self._digest("access", encoded_payload)[:16])
        if not hmac.compare_digest(received_signature, expected_signature):
            raise InvalidTableEntry("Invalid table access token")
        try:
            payload = json.loads(_b64decode(encoded_payload))
            table_id = uuid.UUID(hex=str(payload["tid"]))
            expires_at = datetime.datetime.fromtimestamp(int(payload["exp"]), tz=datetime.UTC)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvalidTableEntry("Invalid table access token") from exc
        current_time = now or datetime.datetime.now(datetime.UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=datetime.UTC)
        if current_time >= expires_at:
            raise InvalidTableEntry("Table access token expired")
        return TableTokenClaims(table_id=table_id, expires_at=expires_at)

    def resolve_code(
        self,
        code: str,
        directory: list[TableDirectoryEntry],
    ) -> TableResolution:
        normalized = code.strip().upper().replace("-", "").replace(" ", "")
        if _MANUAL_CODE_RE.fullmatch(normalized) is None:
            raise InvalidTableEntry("Table code was not found")
        entry = next(
            (item for item in directory if self.build_manual_code(item.table_id) == normalized),
            None,
        )
        if entry is None:
            raise InvalidTableEntry("Table code was not found")
        return TableResolution(
            table_title=entry.table_title,
            hall_title=entry.hall_title,
            service_percent=entry.service_percent,
            manual_code=normalized,
            access_token=self.issue_access_token(entry),
        )

    async def resolve(self, entry: str | None, code: str | None) -> TableResolution:
        resolved_code = self.parse_start_param(entry) if entry is not None else (code or "")
        return self.resolve_code(resolved_code, await get_table_directory())

    async def resolve_access_token(self, token: str) -> TableDirectoryEntry:
        claims = self.verify_access_token(token)
        directory = await get_table_directory()
        entry = next((item for item in directory if item.table_id == claims.table_id), None)
        if entry is None:
            raise InvalidTableEntry("Table is no longer available")
        return entry

    async def restore(
        self,
        table_id: uuid.UUID,
        expires_at: datetime.datetime,
    ) -> TableResolution:
        """Issue fresh customer-safe context for a table recorded on an order."""
        directory = await get_table_directory()
        entry = next((item for item in directory if item.table_id == table_id), None)
        if entry is None:
            raise InvalidTableEntry("Table is no longer available")
        return TableResolution(
            table_title=entry.table_title,
            hall_title=entry.hall_title,
            service_percent=entry.service_percent,
            manual_code=self.build_manual_code(entry.table_id),
            access_token=self.issue_access_token(entry, expires_at=expires_at),
        )

    async def manifest(self) -> list[dict]:
        result: list[dict] = []
        for entry in await get_table_directory():
            start_param = self.build_start_param(entry.table_id)
            result.append(
                {
                    "table_title": entry.table_title,
                    "hall_title": entry.hall_title,
                    "service_percent": float(entry.service_percent),
                    "manual_code": self.build_manual_code(entry.table_id),
                    "start_param": start_param,
                    "deep_link": f"https://t.me/{self._bot_username}?startapp={start_param}",
                }
            )
        return result
