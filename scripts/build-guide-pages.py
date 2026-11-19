#!/usr/bin/env python3
"""Build the static Terento guide pages: Mac installation, troubleshooting, the
Linux web installer guide and the Garmin Edge Mac guide, six locales each.

English is the meaning source. The release label is read from the canonical
application update manifest so the guide cannot drift from the current release.
Troubleshooting copy lives in scripts/templates/troubleshooting-copy.json; its
section anchors are a stable contract because the app links to them.
"""

from __future__ import annotations

import html
import json
import re
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://terento.app"
GUIDE_SLUG = "guides/install-garmin-maps-mac/"
PUBLISHED = "2026-08-28T00:00:00Z"
RELEASE = json.loads((ROOT / "site/updates/macos-arm64.json").read_text())
# dateModified: the later of the release date and the last content review of
# the guide. Bump GUIDE_CONTENT_REVIEWED when the guide text changes; the site
# tests compare it with the sitemap lastmod (2026-11-02 SEO review, A6).
GUIDE_CONTENT_REVIEWED = "2026-11-19"
REVIEWED = max(RELEASE["publishedAt"], GUIDE_CONTENT_REVIEWED) + "T00:00:00Z"
IMAGE_VERSION = "20260912-app-screens-v2"
READING_STATE_VERSION = "20260902-reading-state"
UMAMI_SCRIPT_VERSION = "20261114-umami-monitoring"
SHELL_VERSION = "20260905-in-page-language-v1"
STYLE_VERSION = "20261119-site-refresh-v7"
LANGUAGE_VERSION = "20260905-language-selector-full-name-v1"
SOCIAL_IMAGE = "/assets/social/terento-og.png"
EMAIL_ADDRESS = "hello@terento.app"
TROUBLESHOOTING_SLUG = "guides/troubleshooting/"
TROUBLESHOOTING_PUBLISHED = "2026-10-06T00:00:00Z"
TROUBLESHOOTING_REVIEWED = "2026-11-19T00:00:00Z"
TROUBLESHOOTING_COPY = json.loads((ROOT / "scripts/templates/troubleshooting-copy.json").read_text(encoding="utf-8"))
LINUX_SLUG = "guides/install-garmin-maps-linux/"
LINUX_PUBLISHED = "2026-11-02T00:00:00Z"
LINUX_REVIEWED = "2026-11-19T00:00:00Z"
LINUX_COPY = json.loads((ROOT / "scripts/templates/linux-guide-copy.json").read_text(encoding="utf-8"))
EDGE_SLUG = "guides/install-garmin-maps-edge-mac/"
EDGE_PUBLISHED = "2026-11-05T00:00:00Z"
EDGE_REVIEWED = "2026-11-19T00:00:00Z"
EDGE_COPY = json.loads((ROOT / "scripts/templates/edge-guide-copy.json").read_text(encoding="utf-8"))
WATCH_COPY = json.loads((ROOT / "scripts/templates/watch-guide-copy.json").read_text(encoding="utf-8"))
LOCALES = ("en", "de", "fr", "pl", "cs", "it")
# One udev rule for every Garmin USB device (vendor 091e). The web installer
# itself offers a rule for the connected watch only; this guide is read before
# a watch is chosen. TAG+="uaccess" gives the signed-in user access on
# systemd-logind systems; GROUP="plugdev" covers systems that use that group.
LINUX_UDEV_COMMAND = (
    "echo 'SUBSYSTEM==\"usb\", ATTR{idVendor}==\"091e\", MODE=\"0660\", GROUP=\"plugdev\", TAG+=\"uaccess\"' "
    "| sudo tee /etc/udev/rules.d/70-garmin.rules >/dev/null && sudo udevadm control --reload-rules && sudo udevadm trigger"
)
# Stable public contract: the app opens
# https://terento.app/guides/troubleshooting/#<anchor> for each error. Every
# locale renders exactly these ids. Rename or remove one only together with the
# app's help-link mapping and its tests.
TROUBLESHOOTING_ANCHORS = (
    "connect-watch",
    "garmin-busy",
    "multiple-garmin",
    "usb-mode",
    "connection-timeout",
    "watch-not-responding",
    "model-not-enabled",
    "couldnt-check",
    "catalog-unavailable",
    "download-failed",
    "mac-storage",
    "watch-storage",
    "leftover-map",
    "update-remove",
    "send-report",
)
# TODO(app release): this copy describes the current release only. When the next
# app version ships, revisit in all six locales:
# - send-report: add the in-app "Send report to Terento" option (no GitHub
#   account needed; reference "TR-XXXXXX" after sending; Try again on failure)
#   next to the GitHub flow, and keep the email fallback.
# - connect-watch / connection-timeout / watch-not-responding: mention
#   automatic reconnect and the Cancel / Try again actions if they ship.
# - download-failed: mention that an interrupted download can resume.
# - update-remove: mention "About N min left" estimates if they ship.
# - each section: the app's per-error Help links land on these anchors.


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def troubleshooting_body(item: dict[str, object]) -> str:
    """Render troubleshooting copy, obfuscating the support email in HTML."""
    body = esc(str(item["body"]))
    if not item.get("email_link"):
        return body
    email_link = (
        '<a class="text-link" '
        'href="mailto:hello&#64;terento.app?subject=Terento%20installation%20issue" '
        'data-umami-event="support-link-click" '
        'data-umami-event-location="guide-map-not-visible" '
        'data-umami-event-channel="email">hello&#64;terento.app</a>'
    )
    return body.replace(EMAIL_ADDRESS, email_link) if EMAIL_ADDRESS in body else body + ' ' + email_link


def troubleshooting_title(locale: str, anchor: str) -> str:
    for group in TROUBLESHOOTING_COPY[locale]["groups"]:
        for item in group["items"]:
            if item["anchor"] == anchor:
                return str(item["title"])
    raise ValueError(f"Unknown troubleshooting anchor: {anchor}")


def troubleshooting_href(locale: str, anchor: str) -> str:
    if anchor not in TROUBLESHOOTING_ANCHORS:
        raise ValueError(f"Unknown troubleshooting anchor: {anchor}")
    return f"{localized_path(locale, TROUBLESHOOTING_SLUG)}#{anchor}"


def troubleshooting_related_links(locale: str, anchors: tuple[str, ...], page: str = "guide") -> str:
    """Link an install-guide help item to the matching Troubleshooting sections."""
    if not anchors:
        return ""
    links = ", ".join(
        f'<a href="{troubleshooting_href(locale, anchor)}" data-umami-event="guide-link-click" '
        f'data-umami-event-location="{page}-troubleshooting-{anchor}">{esc(troubleshooting_title(locale, anchor))}</a>'
        for anchor in anchors
    )
    return f' {esc(TROUBLESHOOTING_COPY[locale]["guide_related_label"])} {links}.'


def troubleshooting_step_link(locale: str, anchor: str) -> str:
    return (
        f'<a class="guide-step-link text-link" href="{troubleshooting_href(locale, anchor)}" '
        f'data-umami-event="guide-link-click" data-umami-event-location="guide-step-{anchor}">'
        f'{esc(troubleshooting_title(locale, anchor))}</a>'
    )


def localized_path(locale: str, suffix: str = "") -> str:
    prefix = "" if locale == "en" else f"{locale}/"
    return f"/{prefix}{suffix}"


def image_markup(asset: str, width: int, height: int, alt: str, caption: str) -> str:
    stem = asset.rsplit("/", 1)[-1]
    version = f"?v={IMAGE_VERSION}"
    responsive_widths = tuple(size for size in (640, 960, 1280, 1600) if size < width)
    sources = ", ".join(
        f"/assets/app/optimized/{stem}-{size}.avif{version} {size}w"
        for size in responsive_widths
    )
    webp_sources = ", ".join(
        f"/assets/app/optimized/{stem}-{size}.webp{version} {size}w"
        for size in responsive_widths
    )
    fallback_width = responsive_widths[-1]
    # On phones the screenshot is small: a tap opens the full-size image.
    full = f"/assets/app/optimized/{stem}-{fallback_width}.webp{version}"
    return f'''<figure class="guide-screenshot">
          <a class="guide-screenshot-link" href="{full}" target="_blank" rel="noopener"><picture>
            <source type="image/avif" srcset="{sources}" sizes="(max-width: 760px) 100vw, 42vw">
            <source type="image/webp" srcset="{webp_sources}" sizes="(max-width: 760px) 100vw, 42vw">
            <img src="/assets/app/optimized/{stem}-{fallback_width}.avif{version}" srcset="{sources}" sizes="(max-width: 760px) 100vw, 42vw" width="{width}" height="{height}" loading="lazy" decoding="async" alt="{esc(alt)}">
          </picture></a>
          <figcaption>{esc(caption)}</figcaption>
        </figure>'''


TROUBLESHOOTING_LINK_RE = re.compile(r"\[([^\]]+)\]\(#([a-z-]+)\)")


def troubleshooting_text(value: str) -> str:
    """Escape troubleshooting copy and expand its two supported inline tokens."""
    def anchor(match: re.Match[str]) -> str:
        if match.group(2) not in TROUBLESHOOTING_ANCHORS:
            raise ValueError(f"Unknown troubleshooting anchor: {match.group(2)}")
        return f'<a href="#{match.group(2)}">{match.group(1)}</a>'

    rendered = TROUBLESHOOTING_LINK_RE.sub(anchor, esc(value))
    email_link = (
        '<a href="mailto:hello&#64;terento.app?subject=Terento%20installation%20issue" '
        'data-umami-event="support-link-click" '
        'data-umami-event-location="troubleshooting-send-report" '
        'data-umami-event-channel="email">hello&#64;terento.app</a>'
    )
    return rendered.replace("{email}", email_link)


def troubleshooting_copy(locale: str) -> dict[str, object]:
    copy = TROUBLESHOOTING_COPY[locale]
    anchors = tuple(item["anchor"] for group in copy["groups"] for item in group["items"])
    if anchors != TROUBLESHOOTING_ANCHORS:
        raise ValueError(f"{locale}: troubleshooting anchors must match TROUBLESHOOTING_ANCHORS")
    return copy


def troubleshooting_json_ld(locale: str, copy: dict[str, object]) -> str:
    canonical = f"{BASE_URL}{localized_path(locale, TROUBLESHOOTING_SLUG)}"
    graph = [
        {
            "@type": "Organization",
            "@id": f"{BASE_URL}/#organization",
            "name": "Terento",
            "url": f"{BASE_URL}/",
            "logo": f"{BASE_URL}/assets/logo-sky.svg",
            "sameAs": ["https://github.com/VooZ2/terento"],
        },
        {
            "@type": "Article",
            "@id": f"{canonical}#article",
            "headline": copy["h1"],
            "description": copy["description"],
            "datePublished": TROUBLESHOOTING_PUBLISHED,
            "dateModified": TROUBLESHOOTING_REVIEWED,
            "mainEntityOfPage": {"@id": canonical},
            "inLanguage": locale,
            "image": f"{BASE_URL}{SOCIAL_IMAGE}",
            "publisher": {"@id": f"{BASE_URL}/#organization"},
            "author": {"@id": f"{BASE_URL}/#organization"},
            "about": {"@id": f"{BASE_URL}/#software"},
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{canonical}#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": copy["breadcrumb_home"], "item": f"{BASE_URL}{localized_path(locale)}"},
                {"@type": "ListItem", "position": 2, "name": copy["breadcrumb_current"], "item": canonical},
            ],
        },
    ]
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2)


TROUBLESHOOTING_MORE = {
    "en": "More details", "de": "Mehr Details", "fr": "Plus de détails",
    "pl": "Więcej szczegółów", "cs": "Více podrobností", "it": "Più dettagli",
}
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÝĀ-ŽА-Я„“\"(])")


def split_answer(body: str) -> tuple[str, str]:
    """Split a troubleshooting body into its first sentence (the answer) and the rest."""
    parts = SENTENCE_BREAK.split(body.strip(), maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


def render_troubleshooting(locale: str) -> str:
    """Render the troubleshooting page; metadata and shell are filled by later passes."""
    copy = troubleshooting_copy(locale)
    canonical = f"{BASE_URL}{localized_path(locale, TROUBLESHOOTING_SLUG)}"
    groups = []
    for group in copy["groups"]:
        items = []
        for item in group["items"]:
            steps = "".join(f"<li>{troubleshooting_text(step)}</li>" for step in item["steps"])
            # One-line answer first, then the numbered steps, then the longer explanation
            # in <details> (still in the HTML for crawlers and search).
            answer, more = split_answer(item["body"])
            details = (f'<details class="troubleshooting-more"><summary>{esc(TROUBLESHOOTING_MORE[locale])}</summary>'
                       f'<p>{troubleshooting_text(more)}</p></details>') if more else ""
            items.append(f'''<section class="troubleshooting-item" id="{item["anchor"]}" aria-labelledby="{item["anchor"]}-title">
              <h3 id="{item["anchor"]}-title">{esc(item["title"])}</h3>
              <p class="troubleshooting-answer">{troubleshooting_text(answer)}</p>
              <ol class="troubleshooting-steps steps steps--compact">{steps}</ol>{details}
            </section>''')
        groups.append(f'''<section class="troubleshooting" id="{group["id"]}" aria-labelledby="{group["id"]}-title">
            <div class="guide-section-heading"><h2 id="{group["id"]}-title">{esc(group["title"])}</h2></div>
            <div class="troubleshooting-list">{''.join(items)}</div>
          </section>''')
    groups_markup = "\n          ".join(groups)
    # Not a troubleshooting-item: the app's 15 anchors stay the only topics.
    edge = copy["edge"]
    # Symptom picker (round 5): one card per H2 section, each with its title (a link to the
    # section) and one short line; the problems themselves are the H3s below.
    picker_cards = [f'<div class="card troubleshooting-pick"><p class="troubleshooting-pick-title"><a href="#garmin-edge">{esc(edge["title"])}</a></p>'
                    f'<p class="troubleshooting-pick-line">{esc(edge["line"])}</p></div>']
    picker_cards += [
        f'<div class="card troubleshooting-pick"><p class="troubleshooting-pick-title"><a href="#{group["id"]}">{esc(group["title"])}</a></p>'
        f'<p class="troubleshooting-pick-line">{esc(group["line"])}</p></div>'
        for group in copy["groups"]]
    toc = "".join(picker_cards)
    return f'''<!doctype html>
<html lang="{locale}" data-language="{locale}" data-page="troubleshooting">
  <head>
    <script defer src="/site-shell.js?v={SHELL_VERSION}"></script>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#F7F3EC">
    <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#222A2B">
    <meta name="description" content="{esc(copy["description"])}">
    <meta name="robots" content="index,follow">
    <link rel="canonical" href="{canonical}">
    <title>{esc(copy["title"])}</title>
    <link rel="icon" href="/favicon.ico?v=20260820-4" sizes="any">
    <link rel="icon" href="/favicon.svg?v=20260820-4" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20260820-4">
    <link rel="mask-icon" href="/safari-pinned-tab.svg?v=20260820-4" color="#7898A8">
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="stylesheet" href="/styles.css?v={STYLE_VERSION}">
    <script defer src="/language.js?v={LANGUAGE_VERSION}"></script>
    <script defer src="/privacy-consent.js?v={UMAMI_SCRIPT_VERSION}"></script>
    <script type="application/ld+json">
{troubleshooting_json_ld(locale, copy)}
    </script>
  </head>
  <body>
    <a class="skip-link" href="#main-content" data-umami-event="internal-link-click" data-umami-event-location="skip-link">{esc(copy["skip"])}</a>
    <header class="site-header"></header>
    <main id="main-content" class="guide-main">
      <article class="guide-article">
        <header class="guide-intro page-hero">
          <div class="shell"><div class="hero-copy">
            <h1>{esc(copy["h1"])}</h1>
            <p class="hero-lede guide-lede">{esc(copy["intro"])}</p>
          </div></div>
        </header>

        <nav class="troubleshooting-toc troubleshooting-picker shell" aria-label="{esc(copy["toc_label"])}">{toc}</nav>

        <div class="shell guide-content">
          <section class="guide-preflight" id="garmin-edge" aria-labelledby="garmin-edge-title">
            <div class="guide-section-heading"><h2 id="garmin-edge-title">{esc(edge["title"])}</h2></div>
            <div class="guide-preflight-copy">
              {COMPONENTS["callout"](f'<p>{esc(edge["body"])}</p><a class="text-link" href="{localized_path(locale, EDGE_SLUG)}" data-umami-event="guide-link-click" data-umami-event-location="troubleshooting-edge">{esc(edge["link"])}</a>')}
            </div>
          </section>

          {groups_markup}

          {COMPONENTS["end_cta"](locale, "troubleshooting-bottom")}
        </div>
      </article>
    </main>
    <footer class="site-footer"></footer>
  </body>
</html>
'''


COMPONENTS = runpy.run_path(str(ROOT / "scripts/site_components.py"))
GUIDE_LINK_RE = re.compile(r"\[([^\]]+)\]\(([a-z0-9/#-]+)\)")
# Guide switch (same pill chips as the Compatibility filters): real links to the three
# install guides, never tabs. Linux has the same label everywhere.
GUIDE_SWITCH = {
    "en": ("Choose a guide", "Garmin watch", "Garmin Edge"),
    "de": ("Anleitung wählen", "Garmin-Uhr", "Garmin Edge"),
    "fr": ("Choisir un guide", "Montre Garmin", "Garmin Edge"),
    "pl": ("Wybierz poradnik", "Zegarek Garmin", "Garmin Edge"),
    "cs": ("Vyberte návod", "Hodinky Garmin", "Garmin Edge"),
    "it": ("Scegli una guida", "Orologio Garmin", "Garmin Edge"),
}
# The Mac guides' primary button says the same as the Home hero ("Download for Mac").
HOME_COPY = json.loads((ROOT / "scripts/templates/home-copy.json").read_text(encoding="utf-8"))
# One template renders all three install guides. data-page values and Umami
# location prefixes are contracts used by the shell/metadata passes and tests.
GUIDES = {
    "guide": {"slug": GUIDE_SLUG, "copy": WATCH_COPY, "published": PUBLISHED, "modified": REVIEWED,
              "cta": ("download/", "download-cta-click"), "troubleshooting_link": True},
    "edge-guide": {"slug": EDGE_SLUG, "copy": EDGE_COPY, "published": EDGE_PUBLISHED, "modified": EDGE_REVIEWED,
                   "cta": ("download/", "download-cta-click"), "troubleshooting_link": True},
    "linux-guide": {"slug": LINUX_SLUG, "copy": LINUX_COPY, "published": LINUX_PUBLISHED, "modified": LINUX_REVIEWED,
                    "cta": ("install/", "web-installer-link-click"), "troubleshooting_link": False},
}


def guide_link_event(target: str) -> str:
    # Umami taxonomy: the web installer, Maps and Compatibility links have their own events.
    if target.startswith("install/"):
        return "web-installer-link-click"
    if target.startswith("map-styles/"):
        return "maps-link-click"
    if target.startswith("download/"):
        return "download-cta-click"
    if target.startswith("compatibility/"):
        return "compatibility-link-click"
    if target.startswith("guides/"):
        return "guide-link-click"
    return "internal-link-click"


def guide_text(locale: str, value: str, location: str) -> str:
    """Escape guide copy and turn [label](route/) into a localized, tracked site link."""
    return GUIDE_LINK_RE.sub(
        lambda match: f'<a href="{localized_path(locale, match.group(2))}" data-umami-event="{guide_link_event(match.group(2))}" data-umami-event-location="{location}">{match.group(1)}</a>',
        esc(value),
    )


def guide_json_ld(page: str, locale: str) -> str:
    guide = GUIDES[page]
    copy = guide["copy"][locale]
    canonical = f"{BASE_URL}{localized_path(locale, guide['slug'])}"
    graph = [
        {
            "@type": "Organization",
            "@id": f"{BASE_URL}/#organization",
            "name": "Terento",
            "url": f"{BASE_URL}/",
            "logo": f"{BASE_URL}/assets/logo-sky.svg",
            "sameAs": ["https://github.com/VooZ2/terento"],
        },
        {
            "@type": "Article",
            "@id": f"{canonical}#article",
            "headline": copy["h1"],
            "description": copy["description"],
            "datePublished": guide["published"],
            "dateModified": guide["modified"],
            "mainEntityOfPage": {"@id": canonical},
            "inLanguage": locale,
            "image": f"{BASE_URL}{SOCIAL_IMAGE}",
            "publisher": {"@id": f"{BASE_URL}/#organization"},
            "author": {"@id": f"{BASE_URL}/#organization"},
            "about": {"@id": f"{BASE_URL}/#software"},
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{canonical}#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": copy["breadcrumb_home"], "item": f"{BASE_URL}{localized_path(locale)}"},
                {"@type": "ListItem", "position": 2, "name": copy["breadcrumb_current"], "item": canonical},
            ],
        },
    ]
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2)


def guide_switch(page: str, locale: str) -> str:
    label, watch, edge = GUIDE_SWITCH[locale]
    current = ' aria-current="page"'
    links = "".join(
        f'<a class="chip guide-v2-switch-link" href="{localized_path(locale, GUIDES[target]["slug"])}"'
        f'{current if target == page else ""} data-umami-event="guide-link-click" '
        f'data-umami-event-location="{page}-switch">{esc(name)}</a>'
        for target, name in (("guide", watch), ("edge-guide", edge), ("linux-guide", "Linux"))
    )
    return f'<nav class="chips guide-v2-switch" aria-label="{esc(label)}">{links}</nav>'


def guide_action(page: str, locale: str, where: str) -> str:
    """The guide's primary button: Download for Mac, or Open the web installer on Linux."""
    route, event = GUIDES[page]["cta"]
    copy = GUIDES[page]["copy"][locale]
    label = copy["cta"] if route == "install/" else HOME_COPY[locale]["hero_download"]
    return COMPONENTS["primary_action"](
        localized_path(locale, route), esc(label), "",
        f'data-umami-event="{event}" data-umami-event-location="{page}-{where}"',
        "globe" if route == "install/" else "download",
    )


def render_guide(page: str, locale: str) -> str:
    """Render one install guide; metadata and shell are filled by later passes."""
    guide = GUIDES[page]
    copy = guide["copy"][locale]
    canonical = f"{BASE_URL}{localized_path(locale, guide['slug'])}"
    steps = []
    for index, step in enumerate(copy["steps"], start=1):
        command = (
            f'<div class="guide-command-block"><pre class="guide-command" aria-label="{esc(copy["command_label"])}"><code>{esc(LINUX_UDEV_COMMAND)}</code></pre>'
            f'<button type="button" class="guide-copy" title="{esc(copy["copy_label"])}" data-copy-command data-copied-label="{esc(copy["copied_label"])}" data-umami-event="guide-command-copy" data-umami-event-location="linux-guide">'
            '<svg class="guide-copy-icon" aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><!-- @license lucide-static v0.460.0 - ISC --><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>'
            '<svg class="guide-copied-icon" aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><!-- @license lucide-static v0.460.0 - ISC --><path d="M20 6 9 17l-5-5"/></svg>'
            f'<span class="sr-only" data-copy-text aria-live="polite">{esc(copy["copy_label"])}</span></button></div>'
            if step.get("command") else ""
        )
        substeps = (
            '<ol class="guide-substeps">'
            + "".join(f'<li><h4>{esc(item["title"])}</h4><p>{esc(item["body"])}</p></li>' for item in step["substeps"])
            + "</ol>"
            if step.get("substeps") else ""
        )
        help_link = f'<p>{troubleshooting_step_link(locale, step["help_anchor"])}</p>' if step.get("help_anchor") else ""
        visual = image_markup(**step["image"]) if step.get("image") else ""
        steps.append(f'''<li class="guide-step{"" if visual else " guide-v2-step-text"}">
              <div class="guide-step-content">
                <div class="guide-step-copy">
                  <h3>{esc(step["title"])}</h3>
                  <p>{guide_text(locale, step["body"], f"{page}-step")}</p>{command}{substeps}{help_link}
                </div>
                {visual}
              </div>
            </li>''')
    show = ""
    if copy.get("show_title"):
        email = f'\n            <p>{troubleshooting_body({"body": copy["show_email"], "email_link": True})}</p>' if copy.get("show_email") else ""
        show = f'''
          <section class="guide-v2-section" id="show-map" aria-labelledby="show-map-title">
            <h2 id="show-map-title">{esc(copy["show_title"])}</h2>
            {COMPONENTS["callout"](esc(copy["show_body"]))}{email}
          </section>
'''
    help_items = "".join(
        f'''
              <div class="guide-v2-help-item">
                <h3>{esc(item["title"])}</h3>
                <p>{esc(item["body"])}{troubleshooting_related_links(locale, tuple(item.get("related", ())), page)}</p>
              </div>'''
        for item in copy["help"]
    )
    more_link = (
        f'\n            <p class="guide-v2-more"><a class="text-link" href="{localized_path(locale, TROUBLESHOOTING_SLUG)}" '
        f'data-umami-event="guide-link-click" data-umami-event-location="{page}-troubleshooting">{esc(TROUBLESHOOTING_COPY[locale]["guide_page_link"])}</a></p>'
        if guide["troubleshooting_link"] else ""
    )
    more = "".join(
        f'''
          <section class="guide-v2-section" id="{item["id"]}" aria-labelledby="{item["id"]}-title">
            <h2 id="{item["id"]}-title">{esc(item["title"])}</h2>
            <p>{guide_text(locale, item["body"], f"{page}-content")}</p>
          </section>'''
        for item in copy.get("more", ())
    )
    # Shared end-of-page CTA; on Linux the web installer is the primary (the Mac app can't run there).
    cta_band = COMPONENTS["end_cta"](locale, f"{page}-bottom", web_first=page == "linux-guide")
    needs_note = f'\n            <p>{guide_text(locale, copy["needs_note"], f"{page}-preflight")}</p>' if copy.get("needs_note") else ""
    return f'''<!doctype html>
<html lang="{locale}" data-language="{locale}" data-page="{page}">
  <head>
    <script defer src="/site-shell.js?v={SHELL_VERSION}"></script>
    <script defer src="/reading-state.js?v={READING_STATE_VERSION}"></script>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#F7F3EC">
    <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#222A2B">
    <meta name="description" content="{esc(copy["description"])}">
    <meta name="robots" content="index,follow">
    <link rel="canonical" href="{canonical}">
    <title>{esc(copy["title"])}</title>
    <link rel="icon" href="/favicon.ico?v=20260820-4" sizes="any">
    <link rel="icon" href="/favicon.svg?v=20260820-4" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20260820-4">
    <link rel="mask-icon" href="/safari-pinned-tab.svg?v=20260820-4" color="#7898A8">
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="stylesheet" href="/styles.css?v={STYLE_VERSION}">
    <script defer src="/language.js?v={LANGUAGE_VERSION}"></script>
    <script defer src="/privacy-consent.js?v={UMAMI_SCRIPT_VERSION}"></script>
    <script type="application/ld+json">
{guide_json_ld(page, locale)}
    </script>
  </head>
  <body>
    <a class="skip-link" href="#main-content" data-umami-event="internal-link-click" data-umami-event-location="skip-link">{esc(copy["skip"])}</a>
    <header class="site-header"></header>
    <main id="main-content" class="guide-main">
      <article class="guide-article guide-v2">
        <header class="guide-intro page-hero">
          <div class="shell"><div class="hero-copy">
            {guide_switch(page, locale)}
            <h1>{esc(copy["h1"])}</h1>
            <p class="hero-lede guide-lede">{esc(copy["intro"])}</p>
            <p class="hero-actions guide-hero-action">{guide_action(page, locale, "hero")}</p>
          </div></div>
        </header>

        <div class="shell guide-content">
          <section class="guide-v2-section" id="before-you-start" aria-labelledby="before-you-start-title">
            <h2 id="before-you-start-title">{esc(copy["needs_title"])}</h2>
            <div class="guide-needs"><ul class="checklist">{"".join(f"<li>{esc(need)}</li>" for need in copy["needs"])}</ul>{needs_note}</div>
          </section>

          <section class="guide-v2-section" id="steps" aria-labelledby="steps-title">
            <h2 id="steps-title">{esc(copy["steps_title"])}</h2>
            <ol class="guide-timeline steps">{"".join(steps)}</ol>
          </section>
{show}
          <section class="guide-v2-section" id="troubleshooting" aria-labelledby="troubleshooting-title">
            <h2 id="troubleshooting-title">{esc(copy["help_title"])}</h2>
            <div class="guide-v2-help">{help_items}
            </div>{more_link}
          </section>
{more}
          {cta_band}
        </div>
      </article>
    </main>
    <footer class="site-footer"></footer>
  </body>
</html>
'''


def main() -> None:
    for page, guide in GUIDES.items():
        for locale in LOCALES:
            output = ROOT / "site" / localized_path(locale, guide["slug"]).lstrip("/") / "index.html"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(re.sub(r"[ \t]+\n", "\n", render_guide(page, locale)), encoding="utf-8")
            print(output.relative_to(ROOT))
    for locale in LOCALES:
        output = ROOT / "site" / localized_path(locale, TROUBLESHOOTING_SLUG).lstrip("/") / "index.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(re.sub(r"[ \t]+\n", "\n", render_troubleshooting(locale)), encoding="utf-8")
        print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
