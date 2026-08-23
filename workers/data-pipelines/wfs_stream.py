from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import requests


@dataclass(frozen=True)
class WfsStreamResult:
    path: str
    sha256: str
    feature_count: int
    pages: int
    page_size: int
    last_url: str


def _bounded_int(value: str | int | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def iter_wfs_pages(
    *,
    code: str,
    url: str,
    typename: str,
    srs_name: str = 'EPSG:4326',
    page_size: int | None = None,
    max_pages: int | None = None,
    session: requests.Session | None = None,
) -> Iterator[tuple[int, dict[str, Any], str]]:
    """Yield validated WFS 2.0 GeoJSON pages without accumulating the dataset in RAM.

    Completion is strict: a page equal to page_size at max_pages is rejected because
    the caller cannot prove the source was exhausted. This preserves the existing
    no-partial-publication invariant while allowing very large sources to be spooled.
    """
    if not typename:
        raise RuntimeError(f'{code}: typename is required')
    resolved_page_size = _bounded_int(
        page_size if page_size is not None else os.getenv(f'{code}_SOURCE_PAGE_SIZE'),
        2000,
        1,
        10000,
    )
    resolved_max_pages = _bounded_int(
        max_pages if max_pages is not None else os.getenv(f'{code}_SOURCE_MAX_PAGES'),
        500,
        1,
        5000,
    )
    s = session or requests.Session()
    for page_index in range(resolved_max_pages):
        offset = page_index * resolved_page_size
        params = {
            'service': 'WFS',
            'request': 'GetFeature',
            'version': '2.0.0',
            'outputFormat': 'application/json',
            'typeNames': typename,
            'count': resolved_page_size,
            'startIndex': offset,
            'srsName': srs_name,
        }
        response = s.get(
            url,
            params=params,
            headers={
                'accept': 'application/geo+json,application/json',
                'user-agent': 'LoteDiretorBrasil/19.0.0-rc.3 wfs-stream',
            },
            timeout=180,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('type') != 'FeatureCollection':
            raise RuntimeError(f'{code}: WFS page {page_index + 1} is not a FeatureCollection')
        features = payload.get('features')
        if not isinstance(features, list):
            raise RuntimeError(f'{code}: WFS page {page_index + 1} has no feature list')
        yield page_index, payload, response.url
        if len(features) < resolved_page_size:
            return
    raise RuntimeError(
        f'{code}: pagination reached SOURCE_MAX_PAGES={resolved_max_pages}; refuse partial spool'
    )


def spool_wfs_feature_collection(
    *,
    code: str,
    url: str,
    typename: str,
    srs_name: str = 'EPSG:4326',
    page_size: int | None = None,
    max_pages: int | None = None,
    session: requests.Session | None = None,
    output_path: str | Path | None = None,
) -> WfsStreamResult:
    """Write a canonical GeoJSON FeatureCollection incrementally and hash exact bytes.

    The output is suitable for a source snapshot object. No database or publication
    mutation happens here. The caller may delete the temporary file on any later gate
    failure without ever exposing a partial source publication.
    """
    resolved_page_size = _bounded_int(
        page_size if page_size is not None else os.getenv(f'{code}_SOURCE_PAGE_SIZE'),
        2000,
        1,
        10000,
    )
    if output_path is None:
        fd, temp_name = tempfile.mkstemp(prefix=f'lotediretor-{code.lower()}-', suffix='.geojson')
        os.close(fd)
        path = Path(temp_name)
    else:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    feature_count = 0
    pages = 0
    last_url = url
    first = True

    def write(handle, raw: bytes) -> None:
        handle.write(raw)
        digest.update(raw)

    try:
        with path.open('wb') as handle:
            write(handle, b'{"type":"FeatureCollection","features":[')
            for page_index, payload, page_url in iter_wfs_pages(
                code=code,
                url=url,
                typename=typename,
                srs_name=srs_name,
                page_size=resolved_page_size,
                max_pages=max_pages,
                session=session,
            ):
                pages = page_index + 1
                last_url = page_url
                for feature in payload['features']:
                    if not isinstance(feature, dict):
                        raise RuntimeError(f'{code}: non-object feature on page {pages}')
                    geometry = feature.get('geometry')
                    if geometry is None or not isinstance(geometry, dict) or not geometry.get('type'):
                        raise RuntimeError(f'{code}: feature without geometry on page {pages}')
                    if not first:
                        write(handle, b',')
                    raw = json.dumps(feature, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                    write(handle, raw)
                    first = False
                    feature_count += 1
            write(handle, b']}')
        if feature_count == 0:
            raise RuntimeError(f'{code}: full WFS spool produced zero features')
        return WfsStreamResult(
            path=str(path),
            sha256=digest.hexdigest(),
            feature_count=feature_count,
            pages=pages,
            page_size=resolved_page_size,
            last_url=last_url,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
