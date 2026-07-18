import argparse
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path

MANIFEST_URL = "https://restaurant.labtutor.app/api/tables/manifest"


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def download_manifest(
    url: str,
    output: Path,
    *,
    environ: Mapping[str, str] | None = None,
    opener=None,
) -> Path:
    if output.exists():
        raise FileExistsError(output)
    source = os.environ if environ is None else environ
    token = source.get("ADMIN_JWT")
    if not token:
        raise ValueError("ADMIN_JWT is required")

    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    direct_opener = opener or urllib.request.build_opener(RejectRedirects())
    try:
        with direct_opener.open(request, timeout=30) as response:
            if getattr(response, "status", None) != 200:
                raise ValueError("Manifest endpoint did not return direct HTTP 200")
            body = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError):
        raise ValueError("Manifest endpoint did not return direct HTTP 200") from None

    with output.open("xb") as manifest_file:
        manifest_file.write(body)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = download_manifest(MANIFEST_URL, args.output)
    except (FileExistsError, OSError, ValueError):
        parser.exit(1, "manifest download failed\n")
    print(f"manifest_file={output}")


if __name__ == "__main__":
    main()
