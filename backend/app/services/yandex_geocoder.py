import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = httpx.Timeout(10.0)
_GEOCODER_URL = "https://geocode-maps.yandex.ru/v1"
_SUGGEST_URL = "https://suggest-maps.yandex.ru/v1/suggest"


def _normalize_geocoder_lang(lang: str | None) -> str:
    normalized = (lang or "").strip().lower()
    if normalized == "en":
        return "en_US"
    if normalized in {"ru", "uz"}:
        return "ru_RU"
    if normalized in {"ru_ru", "en_us", "en_ru", "uk_ua", "be_by", "tr_tr"}:
        return normalized.replace("-", "_")
    return "ru_RU"


def _normalize_suggest_lang(lang: str | None) -> str:
    normalized = (lang or "").strip().lower()
    if normalized == "en":
        return "en"
    if normalized in {"ru", "uz"}:
        return "ru"
    return "ru"


def _format_yandex_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = response.text.strip()

    if isinstance(payload, dict):
        for key in ("message", "detail", "error"):
            value = payload.get(key)
            if value:
                return str(value)
        return str(payload)

    if isinstance(payload, list):
        return str(payload)

    return payload or response.reason_phrase


def _extract_first_geo_object(payload: dict[str, Any]) -> dict[str, Any] | None:
    members = (
        payload.get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    geo_objects = [member.get("GeoObject") for member in members if member.get("GeoObject")]
    if not geo_objects:
        return None
    return geo_objects[0]


def _extract_geo_objects(payload: dict[str, Any]) -> list[dict[str, Any]]:
    members = (
        payload.get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    geo_objects = [member.get("GeoObject") for member in members if member.get("GeoObject")]
    if not members:
        return []
    return geo_objects


def _parse_pos(raw_pos: str) -> tuple[float, float]:
    lng_text, lat_text = raw_pos.split()
    return float(lat_text), float(lng_text)


def _yandex_request_headers() -> dict[str, str]:
    referer = (settings.public_app_url or settings.public_backend_url).strip()
    if not referer:
        return {}

    return {"Referer": f"{referer.rstrip('/')}/"}


async def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        try:
            response = await client.get(
                url,
                params=params,
                headers=_yandex_request_headers(),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _format_yandex_error(exc.response)
            logger.warning("Yandex API returned HTTP %s: %s", exc.response.status_code, detail)
            raise RuntimeError(
                f"Yandex API returned {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("Yandex API request failed: %s", exc)
            raise RuntimeError(f"Yandex API request failed: {exc}") from exc

    return response.json()


async def _geocode_request(
    *,
    geocode: str | None = None,
    uri: str | None = None,
    lang: str,
    kind: str | None = None,
    ll: str | None = None,
    spn: str | None = None,
    results: int = 1,
) -> dict[str, Any]:
    if not settings.yandex_maps_api_key:
        raise RuntimeError("YANDEX_MAPS_API_KEY is not configured")

    params: dict[str, Any] = {
        "apikey": settings.yandex_maps_api_key,
        "lang": _normalize_geocoder_lang(lang),
        "format": "json",
        "results": results,
    }

    if geocode:
        params["geocode"] = geocode
        params["sco"] = "longlat"
    if uri:
        params["uri"] = uri
    if kind:
        params["kind"] = kind
    if ll and spn:
        params["ll"] = ll
        params["spn"] = spn

    return await _get_json(_GEOCODER_URL, params)


async def _resolve_uri_to_coordinates(uri: str, lang: str) -> tuple[float, float] | None:
    payload = await _geocode_request(uri=uri, lang=lang)
    geo_object = _extract_first_geo_object(payload)
    if not geo_object:
        return None

    raw_pos = geo_object.get("Point", {}).get("pos")
    if not raw_pos:
        return None

    return _parse_pos(raw_pos)


async def reverse_geocode(lat: float, lng: float, lang: str) -> dict[str, Any]:
    nearby = await nearby_addresses(lat, lng, lang, limit=5)
    geo_object = None
    if nearby:
        nearest_address = nearby[0].get("address") or ""
        return {
            "address": str(nearest_address),
            "name": str(nearby[0].get("title") or nearest_address),
            "description": str(nearby[0].get("subtitle") or ""),
            "nearby": nearby,
        }

    payload = await _geocode_request(
        geocode=f"{lng},{lat}",
        lang=lang,
        kind="house",
    )
    geo_object = _extract_first_geo_object(payload)
    if not geo_object:
        return {"address": "", "name": "", "description": "", "nearby": []}

    metadata = geo_object.get("metaDataProperty", {}).get("GeocoderMetaData", {})
    address = metadata.get("Address", {}).get("formatted") or metadata.get("text") or ""

    return {
        "address": address,
        "name": str(geo_object.get("name") or address),
        "description": str(geo_object.get("description") or ""),
        "nearby": [],
    }


def _build_suggestion_from_geo_object(geo_object: dict[str, Any]) -> dict[str, Any] | None:
    raw_pos = geo_object.get("Point", {}).get("pos")
    if not raw_pos:
        return None

    resolved_lat, resolved_lng = _parse_pos(raw_pos)
    metadata = geo_object.get("metaDataProperty", {}).get("GeocoderMetaData", {})
    title = str(geo_object.get("name") or metadata.get("text") or "")
    subtitle = str(geo_object.get("description") or "")
    address = str(metadata.get("Address", {}).get("formatted") or metadata.get("text") or "")

    return {
        "title": title,
        "subtitle": subtitle,
        "lat": resolved_lat,
        "lng": resolved_lng,
        "address": address,
    }


def _dedupe_suggestions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, float, float]] = set()
    deduped: list[dict[str, Any]] = []

    for item in items:
        key = (
            str(item.get("address") or item.get("title") or ""),
            round(float(item.get("lat") or 0.0), 6),
            round(float(item.get("lng") or 0.0), 6),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped


async def nearby_addresses(lat: float, lng: float, lang: str, limit: int = 5) -> list[dict[str, Any]]:
    payload = await _geocode_request(
        geocode=f"{lng},{lat}",
        lang=lang,
        kind="house",
        results=max(limit, 1),
    )
    geo_objects = _extract_geo_objects(payload)
    suggestions = [
        suggestion
        for suggestion in (_build_suggestion_from_geo_object(geo_object) for geo_object in geo_objects)
        if suggestion is not None
    ]
    return _dedupe_suggestions(suggestions)[:limit]


async def _fallback_suggest_via_geocoder(
    text: str,
    lang: str,
    lat: float | None,
    lng: float | None,
) -> list[dict[str, Any]]:
    ll = None
    spn = None
    if lat is not None and lng is not None:
        ll = f"{lng},{lat}"
        spn = "0.5,0.5"

    payload = await _geocode_request(
        geocode=text,
        lang=lang,
        ll=ll,
        spn=spn,
        results=5,
    )
    geo_objects = _extract_geo_objects(payload)
    suggestions = [
        suggestion
        for suggestion in (_build_suggestion_from_geo_object(geo_object) for geo_object in geo_objects)
        if suggestion is not None
    ]
    return _dedupe_suggestions(suggestions)[:5]


async def suggest(
    text: str,
    lang: str,
    lat: float | None = None,
    lng: float | None = None,
) -> list[dict[str, Any]]:
    query = text.strip()
    if not query:
        return []

    if not settings.yandex_geosuggest_api_key:
        return await _fallback_suggest_via_geocoder(query, lang, lat, lng)

    params: dict[str, Any] = {
        "apikey": settings.yandex_geosuggest_api_key,
        "text": query,
        "lang": _normalize_suggest_lang(lang),
        "types": "geo",
        "results": 5,
        "print_address": 1,
        "attrs": "uri",
    }

    if lat is not None and lng is not None:
        params["ll"] = f"{lng},{lat}"
        params["spn"] = "0.5,0.5"
        params["ull"] = f"{lng},{lat}"

    try:
        payload = await _get_json(_SUGGEST_URL, params)
        results = payload.get("results") or []
        if not results:
            return await _fallback_suggest_via_geocoder(query, lang, lat, lng)
    except RuntimeError as exc:
        logger.warning("Geosuggest request failed, falling back to Geocoder: %s", exc)
        return await _fallback_suggest_via_geocoder(query, lang, lat, lng)

    async def _resolve_item(item: dict[str, Any]) -> dict[str, Any] | None:
        uri = item.get("uri")
        if not uri:
            return None

        coordinates = await _resolve_uri_to_coordinates(uri, lang)
        if not coordinates:
            return None

        item_title = item.get("title", {}).get("text") or ""
        item_subtitle = item.get("subtitle", {}).get("text") or ""
        resolved_lat, resolved_lng = coordinates

        return {
            "title": str(item_title),
            "subtitle": str(item_subtitle),
            "lat": resolved_lat,
            "lng": resolved_lng,
        }

    resolved = await asyncio.gather(*(_resolve_item(item) for item in results))
    suggestions = [item for item in resolved if item is not None]
    if suggestions:
        return _dedupe_suggestions(suggestions)

    return await _fallback_suggest_via_geocoder(query, lang, lat, lng)
