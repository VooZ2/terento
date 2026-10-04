---
name: terento-map-catalog
description: Read Terento’s public map catalog and follow original-provider sources while preserving attribution, licensing, and device-safety boundaries.
---

# Terento public map catalog

Use this skill when an agent needs public map package metadata from Terento.
The catalog is read-only metadata. It does not provide map binaries or grant
permission to install, replace, or remove files on a Garmin device.

## Discover the API

1. Fetch `https://terento.app/.well-known/api-catalog` and follow its
   `service-desc` relation to the current OpenAPI document.
2. Read the OpenAPI document before choosing an endpoint. The current catalog
   including BBBike is `GET https://api.terento.app/maps/catalog-v4.json`.
3. Fetch the catalog as JSON and use its provider, map, region, version,
   attribution, license, availability, and source metadata as applicable.

## Preserve the provider and device boundaries

- Treat catalog membership as metadata, not proof that a package is currently
  available to acquire or compatible with a particular device.
- Preserve provider attribution and licensing information. When a user asks
  to obtain a map, use the package’s original-provider source URL; Terento does
  not host or proxy map binaries.
- Do not infer public device compatibility from a catalog entry. Compatibility
  evidence applies only to the exact reviewed model and variant.
- Do not use catalog data to write to or remove files from a device. Use the
  Terento app’s reviewed installation flow for device operations.
- Do not send device identifiers, manifests, or other private device data to
  the public catalog API.
