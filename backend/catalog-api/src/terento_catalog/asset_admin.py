from __future__ import annotations

import argparse
import json

from .asset_pipeline import AssetPipeline
from .asset_attribution import (
    GENERIC_FALLBACK,
    OFFICIAL_PRODUCT_MEDIA,
    TERENTO_RENDER,
    normalize_asset_source,
)
from .asset_storage import AssetStorage
from .config import Settings
from .db import Database


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare and explicitly publish Terento device assets"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="stage a WebP for review")
    _add_asset_arguments(prepare, source_required=True)

    approve = subparsers.add_parser("approve", help="publish a staged WebP")
    _add_asset_arguments(approve)

    deprecate = subparsers.add_parser("deprecate", help="hide an asset")
    _add_asset_arguments(deprecate)

    args = parser.parse_args()
    settings = Settings.from_env()
    database = Database(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    storage = AssetStorage(settings.asset_root)
    pipeline = AssetPipeline(storage)
    owner = None if args.scope == "GENERIC" else args.device_model_id
    source = _source_metadata(args)

    if args.command == "prepare":
        stored = pipeline.prepare(args.source, args.storage_key)
        database.upsert_device_asset(
            device_model_id=owner,
            asset_type=args.asset_type,
            status="PENDING_REVIEW",
            scope=args.scope,
            sha256=stored.sha256,
            width=stored.width,
            height=stored.height,
            mime_type=stored.mime_type,
            source_url=_validated_source_url(
                args.source_url
                or (args.source if args.source.startswith("https://") else None)
            ),
            license_information=args.license_information,
            attribution=args.attribution,
            source_type=source[0] if source else None,
            source_brand=source[1] if source else None,
            attribution_required=source[2] if source else None,
        )
        _print(stored, status="PENDING_REVIEW", storage_key=args.storage_key)
        return

    if args.command == "approve":
        stored = pipeline.approve(args.storage_key)
        database.upsert_device_asset(
            device_model_id=owner,
            asset_type=args.asset_type,
            status="AVAILABLE",
            scope=args.scope,
            url=stored.url,
            storage_key=stored.storage_key,
            sha256=stored.sha256,
            width=stored.width,
            height=stored.height,
            mime_type=stored.mime_type,
            source_url=_validated_source_url(args.source_url),
            license_information=args.license_information,
            attribution=args.attribution,
            source_type=source[0] if source else None,
            source_brand=source[1] if source else None,
            attribution_required=source[2] if source else None,
            asset_version=args.version,
        )
        _print(stored, status="AVAILABLE", version=args.version or 1)
        return

    database.upsert_device_asset(
        device_model_id=owner,
        asset_type=args.asset_type,
        status="DEPRECATED",
        scope=args.scope,
    )
    print(json.dumps({"status": "DEPRECATED"}, separators=(",", ":")))


def _add_asset_arguments(parser: argparse.ArgumentParser, *, source_required: bool = False) -> None:
    parser.add_argument("--device-model-id")
    parser.add_argument("--asset-type", default="product-image")
    parser.add_argument(
        "--scope",
        choices=("FAMILY", "MODEL", "MODEL_SIZE", "EXACT_VARIANT", "GENERIC"),
        default="MODEL",
    )
    parser.add_argument("--storage-key", required=True)
    parser.add_argument("--source", required=source_required)
    parser.add_argument(
        "--source-url",
        help="official/source URL retained as licensing evidence for a local normalized asset",
    )
    parser.add_argument(
        "--license-information",
        help="record the reviewed source/license note for this asset",
    )
    parser.add_argument("--attribution")
    parser.add_argument(
        "--source-type",
        choices=(OFFICIAL_PRODUCT_MEDIA, TERENTO_RENDER, GENERIC_FALLBACK),
        default=OFFICIAL_PRODUCT_MEDIA,
    )
    parser.add_argument("--source-brand")
    parser.add_argument(
        "--attribution-required",
        action="store_true",
        help="mark the asset as requiring external attribution (official Garmin media)",
    )
    parser.add_argument("--version", type=int)


def _source_metadata(args: argparse.Namespace) -> tuple[str, str, bool] | None:
    if args.command == "deprecate":
        return None
    expected_brand = "Garmin" if args.source_type == OFFICIAL_PRODUCT_MEDIA else "Terento"
    brand = args.source_brand or expected_brand
    try:
        return normalize_asset_source(
            args.source_type,
            brand,
            args.attribution_required,
            required=True,
        )
    except ValueError as exc:
        raise SystemExit(f"invalid asset source metadata: {exc}") from exc


def _validated_source_url(source_url: str | None) -> str | None:
    if source_url is not None and not source_url.startswith("https://"):
        raise SystemExit("asset source URL must use HTTPS")
    return source_url


def _print(stored, **extra: object) -> None:
    document = {
        "storageKey": stored.storage_key,
        "url": stored.url,
        "sha256": stored.sha256,
        "width": stored.width,
        "height": stored.height,
        "sizeBytes": stored.size_bytes,
        **extra,
    }
    print(json.dumps(document, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
