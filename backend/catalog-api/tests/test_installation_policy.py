from datetime import datetime, timezone
import json
import re
import unicodedata
import unittest
from unittest import mock

from pglite_support import PGliteTestCase
from terento_catalog import installation_policy as policy_module
from terento_catalog.installation_policy import (
    GENERATION_LABEL_BASE_MODEL_ALIASES,
    build_installation_policy,
    installation_base_model,
    serialize_installation_policy,
    summarize_installation_catalog,
)


# --- Port of the shipped macOS resolver --------------------------------------
# A line-for-line Python port of InstallationAuthorization.swift and
# GarminDeviceModelNormalizer (DeviceIdentity.swift). Both files are unchanged
# in matching and normalization from v1.0.0-beta.14-build35 through
# v1.0.0-rc.2-build42; only document/record key-set validation differs
# (beta.14-beta.18 exact, rc.1+ subset), so both variants are ported.

STRICT_DOCUMENT_KEYS = {"schemaVersion", "policyVersion", "updatedAt", "manufacturer", "devices"}
STRICT_RECORD_KEYS = {
    "id", "manufacturer", "model", "baseModel", "canonicalModel", "variant",
    "caseSizeMm", "displayType", "screenTechnology", "solar", "inReach",
    "active", "mapCapable", "scope", "installationAuthorization",
}
_VARIANT_TOKENS = re.compile(
    r"\b(?:\d{2,3}\s*mm|sapphire|solar|amoled|mip|microled|inreach|leather|titanium|stainless|silicone)\b",
    re.IGNORECASE,
)
_NEGATIVE_LABELS = re.compile(
    r"\b(?:no|not|without|non)\s*-?\s*(?:solar|inreach|amoled|microled|mip)\b", re.IGNORECASE
)


def app_normalize(value):
    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


def app_canonical_model(raw):
    model = re.sub(r"^garmin\s+", "", raw.strip(), flags=re.IGNORECASE)
    if not model or app_normalize(model).startswith("unknown"):
        return None
    match = _VARIANT_TOKENS.search(model)
    if match:
        model = model[:match.start()]
    model = model.strip().strip("-\u2013\u00b7,").strip()
    return app_normalize(model) if model else None


def app_base_model_from(source):
    return app_canonical_model(_NEGATIVE_LABELS.sub(" ", source))


def _sources(identity, *keys):
    return [identity[k].strip() for k in keys if identity.get(k) and identity[k].strip()]


def app_identity_consistent(identity):
    sources = _sources(identity, "model", "deviceDescription", "garminModelDescription")
    return len({b for b in map(app_base_model_from, sources) if b is not None}) <= 1


def app_identity_base_model(identity):
    preferred = _sources(identity, "deviceDescription", "model")
    return app_base_model_from(preferred[0]) if preferred else None


def _case_sizes(source):
    return {int(re.sub(r"\D", "", m)) for m in re.findall(r"\b[0-9]{2,3}\s*mm\b", app_normalize(source))}


def _screens(source):
    tokens = set(app_normalize(source).split())
    return {label for token, label in (("amoled", "AMOLED"), ("microled", "MicroLED"), ("mip", "MIP")) if token in tokens}


def _canonical_screen(value):
    return {"amoled": "AMOLED", "microled": "MicroLED", "mip": "MIP"}.get(app_normalize(value), app_normalize(value))


def _feature_values(feature, source):
    normalized = app_normalize(source)
    pattern = re.compile(r"\b(?:no|not|without|non)\s*-?\s*" + re.escape(feature) + r"\b")
    values = {False} if pattern.search(normalized) else set()
    if feature in pattern.sub(" ", normalized).split():
        values.add(True)
    return values


def _single(values):
    return next(iter(values)) if len(values) == 1 else None


def app_variant_compatible(identity, record):
    sources = _sources(identity, "model", "deviceDescription", "garminModelDescription", "variant")
    observed_size = _single(set().union(*map(_case_sizes, sources)) if sources else set())
    observed_screen = _single(set().union(*map(_screens, sources)) if sources else set())
    observed_solar = _single(set().union(*(_feature_values("solar", s) for s in sources)) if sources else set())
    observed_inreach = _single(set().union(*(_feature_values("inreach", s) for s in sources)) if sources else set())
    text = " ".join([record["model"], record["canonicalModel"], record["variant"]])
    sizes = _case_sizes(text) | ({record["caseSizeMm"]} if record["caseSizeMm"] is not None else set())
    size = _single(sizes)
    if observed_size is not None and size is not None and observed_size != size:
        return False
    screens = _screens(text) | {_canonical_screen(v) for v in (record["screenTechnology"], record["displayType"]) if v is not None}
    screen = _single(screens)
    if observed_screen is not None and screen is not None and app_normalize(screen) != app_normalize(observed_screen):
        return False
    for feature, observed, value in (("solar", observed_solar, record["solar"]), ("inreach", observed_inreach, record["inReach"])):
        values = _feature_values(feature, text) | ({value} if value is not None else set())
        if observed is not None and _single(values) is not None and observed != _single(values):
            return False
    return True


def app_policy_valid(document, *, strict):
    if document.get("manufacturer") != "Garmin":
        return False
    keys = set(document)
    if (keys != STRICT_DOCUMENT_KEYS) if strict else not STRICT_DOCUMENT_KEYS <= keys:
        return False
    seen = set()
    for record in document["devices"]:
        keys = set(record)
        if (keys != STRICT_RECORD_KEYS) if strict else not STRICT_RECORD_KEYS <= keys:
            return False
        if not isinstance(record["canonicalModel"], str) or not isinstance(record["variant"], str):
            return False  # non-optional String fields fail JSONDecoder
        if record["manufacturer"] != "Garmin" or not record["id"] or not record["model"] or not record["baseModel"]:
            return False
        if record["id"] in seen:
            return False
        seen.add(record["id"])
    return document["schemaVersion"] == 3 and document["policyVersion"] >= 3


def app_resolve(document, identity, *, strict=True):
    """Return (decision, candidate ids) exactly as the shipped client decides."""
    if not app_policy_valid(json.loads(json.dumps(document)), strict=strict):
        return "CATALOG_UNAVAILABLE", []
    if app_normalize(identity.get("manufacturer", "")) != "garmin" or not app_identity_consistent(identity):
        return "PENDING", []
    base = app_identity_base_model(identity)
    if not base:
        return "PENDING", []
    model_records = [r for r in document["devices"]
                     if app_normalize(r["manufacturer"]) == "garmin" and app_normalize(r["baseModel"]) == base]
    candidates = [r for r in model_records if r["active"] and app_variant_compatible(identity, r)]
    ids = sorted(r["id"] for r in candidates)
    if not candidates:
        return ("OUT_OF_SCOPE" if any(not r["active"] for r in model_records) else "PENDING"), ids
    if all(r["mapCapable"] is True for r in candidates):
        approved = candidates[0]
        # InstallationAuthorizationState.matches(identity:) re-checks the
        # approved record before every acquisition and write.
        assert app_normalize(approved["baseModel"]) == base and app_variant_compatible(identity, approved)
        return "APPROVED", ids
    if all(r["mapCapable"] is False for r in candidates):
        return "OUT_OF_SCOPE", ids
    return "PENDING", ids


def garmin(model, **extra):
    return dict(manufacturer="Garmin", model=model, **extra)


def catalog_row(device_id, model, canonical_model, variant, case_size, *, active=True, map_capable=True,
                screen="AMOLED"):
    return dict(device_id=device_id, manufacturer="Garmin", model=model, canonical_model=canonical_model,
                variant=variant, case_size_mm=case_size, display_type=screen, screen_technology=screen,
                solar=None, inreach=None, active=active, map_capable=map_capable)


# Mirrors the live 2026-10-07 epix rows (migrations 020/050 and 016).
EPIX_ROWS = [
    catalog_row("garmin-epix-pro-gen-2", "epix Pro (Gen 2)", "epix pro gen 2", "Historical", None, screen=None),
    catalog_row("garmin-epix-pro-gen-2-42", "epix Pro (Gen 2)", "epix pro gen 2", "42 mm, AMOLED", 42),
    catalog_row("garmin-epix-pro-gen-2-47", "epix Pro (Gen 2)", "epix pro gen 2", "47 mm, AMOLED", 47),
    catalog_row("garmin-epix-pro-gen-2-51", "epix Pro (Gen 2)", "epix pro gen 2", "51 mm, AMOLED", 51),
    catalog_row("garmin-epix-gen-2-47", "epix (Gen 2)", "epix gen 2", "47 mm", 47, screen=None),
    catalog_row("garmin-fenix-8-47-amoled", "fēnix 8", "fenix 8", "47 mm, AMOLED", 47),
]
WHEN = datetime(2026, 10, 9, tzinfo=timezone.utc)


class InstallationPolicyTests(unittest.TestCase):
    def test_base_model_uses_catalog_model_not_variant_rich_canonical_identity(self):
        self.assertEqual(installation_base_model("fēnix 7 Pro"), "fenix 7 pro")
        self.assertEqual(installation_base_model("Garmin fēnix 7 Pro Solar"), "fenix 7 pro")
        self.assertNotEqual(installation_base_model("fēnix 7X Pro"), "fenix 7 pro")
        self.assertNotEqual(installation_base_model("fēnix 8"), "fenix 7 pro")
        self.assertNotEqual(installation_base_model("Edge 840"), "fenix 7 pro")
        rows = [
            dict(device_id="pro", manufacturer="Garmin", model="fēnix 7 Pro",
                 canonical_model="fenix 7 pro", active=True, map_capable=True),
            dict(device_id="solar", manufacturer="Garmin", model="fēnix 7 Pro",
                 canonical_model="fenix 7 pro solar no wifi", active=True, map_capable=False),
        ]
        policy = build_installation_policy(rows, datetime(2026, 9, 22, tzinfo=timezone.utc))
        self.assertEqual({row["baseModel"] for row in policy["devices"]}, {"fenix 7 pro"})

    def test_policy_is_derived_from_active_and_map_capable_only(self):
        rows = [
            {
                "device_id": "fenix-8",
                "manufacturer": "Garmin",
                "model": "fenix 8",
                "canonical_model": "fenix 8",
                "variant": "47 mm AMOLED",
                "case_size_mm": 47,
                "display_type": "AMOLED",
                "active": True,
                "map_capable": True,
                "support_status": "NOT_EVALUATED",
                "successful_install_count": 0,
            },
            {
                "device_id": "fenix-7",
                "manufacturer": "Garmin",
                "model": "fenix 8",
                "canonical_model": "fenix 7",
                "variant": "51 mm AMOLED",
                "case_size_mm": 51,
                "display_type": "AMOLED",
                "active": True,
                "map_capable": True,
                "support_status": "UNSUPPORTED",
            },
            {
                "device_id": "enduro-3",
                "manufacturer": "Garmin",
                "model": "Enduro 3",
                "canonical_model": "Enduro 3",
                "variant": "51 mm",
                "case_size_mm": 51,
                "display_type": "MIP",
                "active": True,
                "map_capable": True,
                "support_status": "NOT_EVALUATED",
            },
            {
                "device_id": "edge-840",
                "manufacturer": "Garmin",
                "model": "Edge 840",
                "canonical_model": "Edge 840",
                "variant": "",
                "active": True,
                "map_capable": False,
                "support_status": "SUPPORTED",
            },
            {
                "device_id": "unknown-capability",
                "manufacturer": "Garmin",
                "model": "future model",
                "canonical_model": "future model",
                "variant": "",
                "active": True,
                "map_capable": None,
                "support_status": "SUPPORTED",
            },
            {
                "device_id": "inactive-map-model",
                "manufacturer": "Garmin",
                "model": "retired model",
                "canonical_model": "retired model",
                "variant": "",
                "active": False,
                "map_capable": True,
                "support_status": "SUPPORTED",
            },
        ]

        policy = build_installation_policy(
            rows, datetime(2026, 9, 22, tzinfo=timezone.utc)
        )

        by_id = {row["id"]: row for row in policy["devices"]}
        self.assertEqual(policy["schemaVersion"], 3)
        self.assertEqual(policy["policyVersion"], 3)
        self.assertEqual(by_id["fenix-8"]["baseModel"], "fenix 8")
        self.assertEqual(by_id["fenix-8"]["installationAuthorization"], "APPROVED")
        self.assertEqual(by_id["fenix-7"]["installationAuthorization"], "APPROVED")
        self.assertEqual(by_id["enduro-3"]["installationAuthorization"], "APPROVED")
        self.assertEqual(by_id["edge-840"]["scope"], "OUT_OF_SCOPE")
        self.assertEqual(by_id["edge-840"]["installationAuthorization"], "BLOCKED")
        self.assertEqual(by_id["unknown-capability"]["installationAuthorization"], "PENDING")
        self.assertEqual(by_id["inactive-map-model"]["installationAuthorization"], "BLOCKED")
        self.assertNotIn("supportStatus", by_id["fenix-7"])
        self.assertNotIn("successful_install_count", policy)

        summary = summarize_installation_catalog(rows)
        self.assertEqual(summary["mapCapableTrue"], 4)
        self.assertEqual(summary["mapCapableFalse"], 1)
        self.assertEqual(summary["mapCapableNull"], 1)
        self.assertEqual(summary["activeMapCapableTrueApproved"], 3)
        self.assertEqual(summary["activeMapCapableFalseBlocked"], 1)
        self.assertEqual(summary["activeMapCapableNullPending"], 1)

        active_yes = [row for row in policy["devices"] if row["active"] and row["mapCapable"] is True]
        self.assertTrue(all(row["installationAuthorization"] == "APPROVED" for row in active_yes))



class GenerationLabelAliasTests(unittest.TestCase):
    def policy(self, rows=EPIX_ROWS, aliases=None):
        if aliases is None:
            return build_installation_policy(rows, WHEN)
        with mock.patch.dict(policy_module.GENERATION_LABEL_BASE_MODEL_ALIASES, aliases, clear=True):
            return build_installation_policy(rows, WHEN)

    def test_alias_table_is_exact_reviewed_and_normalized(self):
        self.assertEqual(GENERATION_LABEL_BASE_MODEL_ALIASES, {"epix pro": "epix pro gen 2"})
        for alias, target in GENERATION_LABEL_BASE_MODEL_ALIASES.items():
            self.assertEqual(installation_base_model(alias), alias)
            self.assertEqual(installation_base_model(target), target)
            self.assertNotEqual(alias, target)
            # An alias is a whole reported name, never a family or prefix.
            self.assertEqual(app_base_model_from(alias.upper()), alias)

    def test_alias_rows_mirror_every_target_row(self):
        policy = self.policy()
        devices = policy["devices"]
        real = {d["id"]: d for d in devices if d["baseModel"] == "epix pro gen 2"}
        aliases = {d["id"]: d for d in devices if d["baseModel"] == "epix pro"}
        self.assertEqual(len(real), 4)
        self.assertEqual(set(aliases), {f"{i}@alias-epix-pro" for i in real})
        for alias_id, alias in aliases.items():
            source = real[alias_id.removesuffix("@alias-epix-pro")]
            self.assertEqual({k: v for k, v in alias.items() if k not in ("id", "baseModel")},
                             {k: v for k, v in source.items() if k not in ("id", "baseModel")})
        self.assertEqual(len(devices), len(EPIX_ROWS) + 4)
        self.assertEqual(len({d["id"] for d in devices}), len(devices))
        self.assertEqual([d["id"] for d in devices], sorted(d["id"] for d in devices))
        self.assertEqual(policy["schemaVersion"], 3)
        self.assertEqual(policy["policyVersion"], 3)

    def test_alias_inherits_null_false_and_inactive_capability(self):
        rows = [
            catalog_row("garmin-epix-pro-gen-2-42", "epix Pro (Gen 2)", "epix pro gen 2", "42 mm, AMOLED", 42, map_capable=None),
            catalog_row("garmin-epix-pro-gen-2-47", "epix Pro (Gen 2)", "epix pro gen 2", "47 mm, AMOLED", 47, map_capable=False),
            catalog_row("garmin-epix-pro-gen-2-51", "epix Pro (Gen 2)", "epix pro gen 2", "51 mm, AMOLED", 51, active=False),
        ]
        by_id = {d["id"]: d for d in self.policy(rows)["devices"]}
        null = by_id["garmin-epix-pro-gen-2-42@alias-epix-pro"]
        self.assertIsNone(null["mapCapable"])
        self.assertEqual((null["scope"], null["installationAuthorization"]), ("UNKNOWN", "PENDING"))
        no = by_id["garmin-epix-pro-gen-2-47@alias-epix-pro"]
        self.assertIs(no["mapCapable"], False)
        self.assertEqual(no["installationAuthorization"], "BLOCKED")
        inactive = by_id["garmin-epix-pro-gen-2-51@alias-epix-pro"]
        self.assertIs(inactive["active"], False)
        self.assertEqual(inactive["installationAuthorization"], "BLOCKED")
        policy = self.policy(rows)
        self.assertEqual(app_resolve(policy, garmin("EPIX PRO 42mm"))[0], "PENDING")
        self.assertEqual(app_resolve(policy, garmin("EPIX PRO 47mm"))[0], "OUT_OF_SCOPE")
        self.assertEqual(app_resolve(policy, garmin("EPIX PRO 51mm"))[0], "OUT_OF_SCOPE")
        self.assertEqual(app_resolve(policy, garmin("EPIX PRO"))[0], "PENDING")

    def test_no_alias_rows_for_unrelated_or_absent_models(self):
        rows = [row for row in EPIX_ROWS if row["canonical_model"] != "epix pro gen 2"]
        devices = self.policy(rows)["devices"]
        self.assertEqual(len(devices), len(rows))
        self.assertFalse(any("@alias-" in d["id"] for d in devices))
        self.assertEqual({d["baseModel"] for d in self.policy()["devices"]},
                         {"epix pro gen 2", "epix pro", "epix gen 2", "fenix 8"})

    def test_real_catalog_rows_for_the_alias_name_take_precedence(self):
        rows = [*EPIX_ROWS, catalog_row("garmin-epix-pro", "epix Pro", "epix pro", "", None, map_capable=None)]
        devices = self.policy(rows)["devices"]
        self.assertEqual([d["id"] for d in devices if d["baseModel"] == "epix pro"], ["garmin-epix-pro"])

    def test_alias_id_collision_fails_closed(self):
        rows = [*EPIX_ROWS, catalog_row("garmin-epix-pro-gen-2-42@alias-epix-pro", "Other", "other", "", None)]
        with self.assertRaises(ValueError):
            self.policy(rows)

    def test_shipped_resolver_approves_reported_epix_pro_with_size_narrowing(self):
        before = self.policy(aliases={})
        after = self.policy()
        unsized = "garmin-epix-pro-gen-2@alias-epix-pro"
        cases = {
            "EPIX PRO": {unsized, *(f"garmin-epix-pro-gen-2-{s}@alias-epix-pro" for s in (42, 47, 51))},
            "epix Pro 51mm": {unsized, "garmin-epix-pro-gen-2-51@alias-epix-pro"},
            "EPIX PRO 47mm": {unsized, "garmin-epix-pro-gen-2-47@alias-epix-pro"},
            "Garmin epix Pro 42 mm": {unsized, "garmin-epix-pro-gen-2-42@alias-epix-pro"},
            # Edition words are variant tokens, so the base model is still "epix pro".
            "epix Pro Sapphire": {unsized, *(f"garmin-epix-pro-gen-2-{s}@alias-epix-pro" for s in (42, 47, 51))},
        }
        for reported, expected in cases.items():
            for strict in (True, False):
                with self.subTest(reported=reported, strict=strict):
                    self.assertEqual(app_resolve(before, garmin(reported), strict=strict), ("PENDING", []))
                    self.assertEqual(app_resolve(after, garmin(reported), strict=strict),
                                     ("APPROVED", sorted(expected)))
        # The same report through MTP description and XML model text.
        identity = garmin("EPIX PRO", deviceDescription="epix Pro 51mm", garminModelDescription="EPIX PRO")
        self.assertEqual(app_resolve(after, identity),
                         ("APPROVED", sorted({unsized, "garmin-epix-pro-gen-2-51@alias-epix-pro"})))

    def test_other_base_models_are_unchanged(self):
        before = self.policy(aliases={})
        after = self.policy()
        for reported in ("epix", "EPIX 47mm", "epix (Gen 2)", "epix Gen 2", "epix Pro (Gen 2) 51mm",
                         "EPIX PRO GEN 2", "epix Pro Gen 3", "epix Pro 2", "fēnix 8 47mm", "Edge 840"):
            with self.subTest(reported=reported):
                self.assertEqual(app_resolve(after, garmin(reported)), app_resolve(before, garmin(reported)))
        self.assertEqual(app_resolve(after, garmin("epix")), ("PENDING", []))
        self.assertEqual(app_resolve(after, garmin("epix (Gen 2)")), ("APPROVED", ["garmin-epix-gen-2-47"]))
        self.assertEqual(app_resolve(after, garmin("epix Pro (Gen 2) 51mm")),
                         ("APPROVED", ["garmin-epix-pro-gen-2", "garmin-epix-pro-gen-2-51"]))
        # A base-model conflict between reported sources stays PENDING.
        self.assertEqual(app_resolve(after, garmin("EPIX PRO", garminModelDescription="epix (Gen 2)")),
                         ("PENDING", []))

    def test_shipped_strict_and_tolerant_parsers_accept_the_aliased_policy(self):
        document = json.loads(serialize_installation_policy(self.policy()))
        self.assertTrue(app_policy_valid(document, strict=True))
        self.assertTrue(app_policy_valid(document, strict=False))
        # Reusing the real ids would make every shipped client fail closed.
        duplicated = json.loads(json.dumps(document))
        for device in duplicated["devices"]:
            device["id"] = device["id"].split("@", 1)[0]
        self.assertFalse(app_policy_valid(duplicated, strict=True))
        self.assertFalse(app_policy_valid(duplicated, strict=False))


class MigratedCatalogAliasTests(PGliteTestCase):
    def test_migrated_catalog_policy_approves_reported_epix_pro(self):
        rows, updated_at = self.db.installation_policy_snapshot()
        policy = build_installation_policy(rows, updated_at)
        document = json.loads(serialize_installation_policy(policy))
        self.assertTrue(app_policy_valid(document, strict=True))
        real = {d["id"] for d in document["devices"] if d["baseModel"] == "epix pro gen 2"}
        alias = {d["id"] for d in document["devices"] if d["baseModel"] == "epix pro"}
        self.assertEqual(real, {"garmin-epix-pro-gen-2", "garmin-epix-pro-gen-2-42",
                                "garmin-epix-pro-gen-2-47", "garmin-epix-pro-gen-2-51"})
        self.assertEqual(alias, {f"{i}@alias-epix-pro" for i in real})
        self.assertEqual(len(document["devices"]), len(rows) + len(real))
        self.assertEqual(app_resolve(document, garmin("epix Pro 51mm")),
                         ("APPROVED", ["garmin-epix-pro-gen-2-51@alias-epix-pro", "garmin-epix-pro-gen-2@alias-epix-pro"]))
        # Plain "epix" is a real catalog row since migration 075 (the original
        # epix), not an alias; both epix generations are maps-capable.
        self.assertEqual(app_resolve(document, garmin("epix")), ("APPROVED", ["garmin-epix-gen-1"]))
        self.assertNotIn("epix", GENERATION_LABEL_BASE_MODEL_ALIASES)


if __name__ == "__main__":
    unittest.main()
