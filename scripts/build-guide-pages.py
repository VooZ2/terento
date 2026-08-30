#!/usr/bin/env python3
"""Build the six static Terento Mac installation guide pages.

English is the meaning source. The release label is read from the canonical
application update manifest so the guide cannot drift from the current beta.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://terento.app"
GUIDE_SLUG = "guides/install-garmin-maps-mac/"
PUBLISHED = "2026-08-28"
REVIEWED = "2026-08-28"
SOCIAL_IMAGE = "/assets/social/terento-og.png"
ISSUES_URL = "https://github.com/VooZ2/terento/issues"
EMAIL_URL = "mailto:hello@terento.app?subject=Terento%20installation%20issue"
EMAIL_ADDRESS = "hello@terento.app"
GARMIN_BASECAMP_URL = "https://support.garmin.com/en-GB/?faq=bcmC4za1sy9hykGnopP8l7&identifier=310&tab=topics"
GARMIN_EXPRESS_URL = "https://support.garmin.com/en-US/?faq=4QVp7mKSIA1LDk5fc1OHX8"
APPLE_ROSETTA_URL = "https://support.apple.com/en-ca/102527"


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def link(label: str, href: str, *, external: bool = False) -> str:
    rel = ' rel="noopener noreferrer"' if external else ""
    return f'<a href="{esc(href)}"{rel}>{esc(label)}</a>'


def localized_path(locale: str, suffix: str = "") -> str:
    prefix = "" if locale == "en" else f"{locale}/"
    return f"/{prefix}{suffix}"


def image_markup(asset: str, width: int, height: int, alt: str, caption: str) -> str:
    stem = asset.rsplit("/", 1)[-1]
    sources = ", ".join(
        f"/assets/app/optimized/{stem}-{size}.avif {size}w"
        for size in (640, 960, 1280, 1600)
    )
    webp_sources = ", ".join(
        f"/assets/app/optimized/{stem}-{size}.webp {size}w"
        for size in (640, 960, 1280, 1600)
    )
    return f'''<figure class="guide-screenshot">
          <picture>
            <source type="image/avif" srcset="{sources}" sizes="(max-width: 760px) 100vw, 42vw">
            <source type="image/webp" srcset="{webp_sources}" sizes="(max-width: 760px) 100vw, 42vw">
            <img src="/assets/app/optimized/{stem}-960.avif" srcset="/assets/app/optimized/{stem}-640.avif 640w, /assets/app/optimized/{stem}-960.avif 960w, /assets/app/optimized/{stem}-1280.avif 1280w, /assets/app/optimized/{stem}-1600.avif 1600w" sizes="(max-width: 760px) 100vw, 42vw" width="{width}" height="{height}" loading="lazy" decoding="async" alt="{esc(alt)}">
          </picture>
          <figcaption>{esc(caption)}</figcaption>
        </figure>'''


def support_actions(copy: dict[str, str]) -> str:
    return f'''<div class="guide-support-actions">
              <a class="text-link" href="{ISSUES_URL}" target="_blank" rel="noopener noreferrer" data-umami-event="support-link-click" data-umami-event-location="guide-install-failed" data-umami-event-channel="github-issue">{esc(copy["open_issue"])} <span aria-hidden="true">→</span></a>
              <a class="text-link" href="{EMAIL_URL}" data-umami-event="support-link-click" data-umami-event-location="guide-install-failed" data-umami-event-channel="email">{esc(copy["email_log"])} <span aria-hidden="true">→</span></a>
            </div>'''


def guide_json_ld(locale: str, copy: dict[str, object], release: str) -> str:
    canonical = f"{BASE_URL}{localized_path(locale, GUIDE_SLUG)}"
    graph = [
        {
            "@type": "Article",
            "@id": f"{canonical}#article",
            "headline": copy["h1"],
            "description": copy["meta_description"],
            "datePublished": PUBLISHED,
            "dateModified": REVIEWED,
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


def render(locale: str, copy: dict[str, object], release: dict[str, object]) -> str:
    canonical = f"{BASE_URL}{localized_path(locale, GUIDE_SLUG)}"
    home = localized_path(locale)
    download = localized_path(locale, "download/")
    compatibility = localized_path(locale, "compatibility/")
    release_label = str(release["releaseLabel"])
    alternate_links = "\n".join(
        f'    <link rel="alternate" hreflang="{candidate}" href="{BASE_URL}{localized_path(candidate, GUIDE_SLUG)}">'
        for candidate in ("en", "de", "fr", "pl", "cs", "it")
    )
    meta_locale = {"en": "en_US", "de": "de_DE", "fr": "fr_FR", "pl": "pl_PL", "cs": "cs_CZ", "it": "it_IT"}[locale]
    timeline = []
    for index, step in enumerate(copy["steps"], 1):
        visual = ""
        if step.get("image"):
            visual = image_markup(**step["image"])
        timeline.append(f'''<li class="guide-step">
              <div class="guide-step-marker" aria-hidden="true">{index:02d}</div>
              <div class="guide-step-content">
                <div class="guide-step-copy">
                  <h3>{esc(step["title"])}</h3>
                  <p>{esc(step["body"])}</p>
                  {f'<p class="guide-step-note">{esc(step["note"])}</p>' if step.get("note") else ""}
                  {f'<a class="guide-step-link text-link" href="{download}">{esc(step["link_label"])} <span aria-hidden="true">→</span></a>' if step.get("link_label") else ""}
                </div>
                {visual}
              </div>
            </li>''')
    troubleshooting = []
    for item in copy["troubleshooting"]:
        actions = support_actions(copy) if item.get("support_links") else ""
        troubleshooting.append(f'''<section class="troubleshooting-item">
              <h3>{esc(item["title"])}</h3>
              <p>{esc(item["body"]) if not item.get("support_links") else item["body"].replace(EMAIL_ADDRESS, link(EMAIL_ADDRESS, EMAIL_URL))}</p>
              {actions}
            </section>''')
    source_copy = copy["sources"]
    source_html = source_copy["body"].replace("[BaseCamp]", link("BaseCamp", GARMIN_BASECAMP_URL, external=True))
    source_html = source_html.replace("[Garmin Express]", link("Garmin Express", GARMIN_EXPRESS_URL, external=True))
    source_html = source_html.replace("[Rosetta]", link("Rosetta", APPLE_ROSETTA_URL, external=True))
    guide_json = guide_json_ld(locale, copy, release_label)
    return f'''<!doctype html>
<html lang="{locale}" data-language="{locale}" data-page="guide">
  <head>
    <script defer src="/site-shell.js?v=20260828-guide"></script>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#F7F3EC">
    <meta name="description" content="{esc(copy["meta_description"])}">
    <meta name="robots" content="index,follow">
    <link rel="canonical" href="{canonical}">
{alternate_links}
    <link rel="alternate" hreflang="x-default" href="{BASE_URL}/{GUIDE_SLUG}">
    <meta property="og:type" content="article">
    <meta property="og:site_name" content="Terento">
    <meta property="og:title" content="{esc(copy["title"])}">
    <meta property="og:description" content="{esc(copy["meta_description"])}">
    <meta property="og:url" content="{canonical}">
    <meta property="og:image" content="{BASE_URL}{SOCIAL_IMAGE}">
    <meta property="og:image:type" content="image/png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:image:alt" content="Terento showing a connected Garmin smartwatch on macOS">
    <meta property="og:locale" content="{meta_locale}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{esc(copy["title"])}">
    <meta name="twitter:description" content="{esc(copy["meta_description"])}">
    <meta name="twitter:image" content="{BASE_URL}{SOCIAL_IMAGE}">
    <title>{esc(copy["title"])}</title>
    <link rel="icon" href="/favicon.ico?v=20260820-4" sizes="any">
    <link rel="icon" href="/favicon.svg?v=20260820-4" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20260820-4">
    <link rel="mask-icon" href="/safari-pinned-tab.svg?v=20260820-4" color="#7898A8">
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="stylesheet" href="/styles.css?v=20260828-guide">
    <script defer src="/language.js?v=20260824-2"></script>
    <script defer src="/privacy-consent.js?v=20260826-2"></script>
    <script type="application/ld+json">
{guide_json}
    </script>
  </head>
  <body>
    <a class="skip-link" href="#main-content">{esc(copy["skip"])}</a>
    <header class="site-header"></header>
    <main id="main-content" class="guide-main">
      <article class="guide-article">
        <header class="guide-intro">
          <div class="shell">
            <p class="eyebrow"><span class="status-dot" aria-hidden="true"></span>{esc(copy["eyebrow"])}</p>
            <h1>{esc(copy["h1"])}</h1>
            <p class="guide-lede">{esc(copy["intro"])}</p>
            <div class="guide-actions">
              <a class="download-action" href="{download}" data-umami-event="download-cta-click" data-umami-event-location="guide-hero">{esc(copy["download_beta"])} <span aria-hidden="true">→</span></a>
              <a class="text-link" href="{compatibility}" data-umami-event="compatibility-link-click" data-umami-event-location="guide-preflight">{esc(copy["see_compatibility"])} <span aria-hidden="true">→</span></a>
            </div>
            <p class="guide-facts"><span>macOS 13+</span><span aria-hidden="true">·</span><span>Apple Silicon</span><span aria-hidden="true">·</span><span>{esc(copy["current_beta"])}</span></p>
            <p class="guide-meta"><span><strong>{esc(copy["last_reviewed"])}:</strong> <time datetime="{REVIEWED}">{esc(copy["reviewed_date"])}</time></span><span aria-hidden="true">·</span><span><strong>{esc(copy["applies_to"])}:</strong> Terento {esc(release_label)}</span></p>
          </div>
        </header>

        <div class="shell guide-content">
          <section class="guide-preflight" id="before-you-start" aria-labelledby="before-you-start-title">
            <div class="guide-section-heading"><p class="eyebrow">{esc(copy["before_eyebrow"])}</p><h2 id="before-you-start-title">{esc(copy["before_title"])}</h2></div>
            <div class="guide-preflight-copy">
              <ul class="guide-checklist">{''.join(f'<li>{esc(item)}</li>' for item in copy["checklist"])}</ul>
              <p>{esc(copy["compatibility_note"])}</p>
              <a class="text-link" href="{compatibility}" data-umami-event="compatibility-link-click" data-umami-event-location="guide-preflight">{esc(copy["see_compatibility_evidence"])} <span aria-hidden="true">→</span></a>
            </div>
          </section>

          <section class="guide-steps" aria-labelledby="steps-title">
            <div class="guide-section-heading"><p class="eyebrow">{esc(copy["steps_eyebrow"])}</p><h2 id="steps-title">{esc(copy["steps_title"])}</h2></div>
            <ol class="guide-timeline">{''.join(timeline)}</ol>
          </section>

          <section class="guide-after-steps" aria-label="{esc(copy["after_steps_label"])}">
            <p>{esc(copy["after_steps_copy"])}</p>
            <a class="download-action" href="{download}" data-umami-event="download-cta-click" data-umami-event-location="guide-after-steps">{esc(copy["download_beta"])} <span aria-hidden="true">→</span></a>
          </section>

          <section class="troubleshooting" id="troubleshooting" aria-labelledby="troubleshooting-title">
            <div class="guide-section-heading"><p class="eyebrow">{esc(copy["troubleshooting_eyebrow"])}</p><h2 id="troubleshooting-title">{esc(copy["troubleshooting_title"])}</h2></div>
            <div class="troubleshooting-list">{''.join(troubleshooting)}</div>
          </section>

          <section class="guide-faq-link" aria-label="{esc(copy["faq_link_eyebrow"])}">
            <div class="guide-faq-link-copy"><p class="eyebrow">{esc(copy["faq_link_eyebrow"])}</p><p>{esc(copy["faq_link_text"])}</p></div>
            <a class="text-link" href="{home}#faq" data-umami-event="faq-link-click" data-umami-event-location="guide-troubleshooting">{esc(copy["faq_link_label"])} <span aria-hidden="true">→</span></a>
          </section>

          <section class="guide-context" aria-labelledby="context-title">
            <div class="guide-section-heading"><p class="eyebrow">{esc(copy["sources"]["eyebrow"])}</p><h2 id="context-title">{esc(copy["sources"]["title"])}</h2></div>
            <div class="guide-context-copy"><p>{source_html}</p><p>{esc(copy["sources"]["limitation"])}</p></div>
          </section>

          <section class="guide-bottom-cta" aria-labelledby="guide-bottom-title">
            <div><p class="eyebrow">{esc(copy["bottom_eyebrow"])}</p><h2 id="guide-bottom-title">{esc(copy["bottom_title"])}</h2></div>
            <a class="download-action" href="{download}" data-umami-event="download-cta-click" data-umami-event-location="guide-bottom">{esc(copy["download_beta"])} <span aria-hidden="true">→</span></a>
          </section>
        </div>
      </article>
    </main>
    <footer class="site-footer"></footer>
  </body>
</html>
'''


COMMON = {
    "en": {
        "title": "How to Install Third-Party Maps on a Garmin Watch from a Mac — Terento",
        "h1": "How to install third-party maps on a Garmin watch from a Mac",
        "meta_description": "Install third-party maps on a compatible Garmin watch from an Apple Silicon Mac with Terento. Connect, choose a region, review storage and install safely.",
        "eyebrow": "Mac installation guide",
        "intro": "Installing third-party maps on a Garmin watch from a Mac can involve MTP, manual file transfers or older desktop tools. Terento provides a native Apple Silicon workflow: connect your watch, choose a region, review storage and install.",
        "download_beta": "Download the beta",
        "see_compatibility": "See compatibility",
        "see_compatibility_evidence": "See current compatibility evidence",
        "current_beta": "Current beta uses Freizeitkarte",
        "last_reviewed": "Last reviewed",
        "reviewed_date": "August 28, 2026",
        "applies_to": "Applies to",
        "skip": "Skip to content",
        "breadcrumb_home": "Home",
        "breadcrumb_current": "Install third-party maps on Garmin from a Mac",
        "before_eyebrow": "A quick check",
        "before_title": "Before you start",
        "checklist": ["Apple Silicon Mac", "macOS 13 or later", "Garmin smartwatch with map support", "USB cable that supports data transfer", "Latest Terento beta", "Enough free storage on the watch"],
        "compatibility_note": "The Compatibility page shows exact models and variants with real installation evidence. It is not a complete list of every Garmin watch that may work. After connection, Terento checks the detected device and tells you whether installation can safely continue.",
        "steps_eyebrow": "The workflow",
        "steps_title": "Install in five steps",
        "after_steps_label": "Next step",
        "after_steps_copy": "The watch stays protected while Terento checks the source, storage, transfer and result.",
        "troubleshooting_eyebrow": "Need a hand?",
        "troubleshooting_title": "If something does not work",
        "open_issue": "Open an issue",
        "email_log": "Email the log",
        "sources": {
            "eyebrow": "A little context",
            "title": "Why a native Mac workflow matters",
            "body": "Garmin currently describes [BaseCamp] for Mac as intended for Intel-based Macs and says Rosetta may enable it on Apple silicon. Garmin gives similar guidance for [Garmin Express]. Apple explains how [Rosetta] lets Intel apps run on Apple silicon. Terento is native for Apple Silicon and focuses specifically on installing and managing third-party maps.",
            "limitation": "Terento does not replace Garmin Express for official device updates or BaseCamp for broader route-planning workflows.",
        },
        "faq_link_eyebrow": "More help",
        "faq_link_text": "Still have questions?",
        "faq_link_label": "See the full FAQ",
        "bottom_eyebrow": "Ready when you are",
        "bottom_title": "Put the map you need on your watch.",
        "steps": [
            {"title": "Download Terento", "body": "Download the latest notarized beta, open the DMG and move Terento to Applications.", "note": "Apple Silicon and macOS 13 or later are required."},
            {"title": "Connect your Garmin", "body": "Connect the watch with a USB data cable. Garmin watches that use MTP may take 1–2 minutes to appear, so keep the device connected and give Terento time to finish detection.", "note": "Close Garmin Express, OpenMTP or another app that may already be using the watch.", "image": {"asset": "your-garmin", "width": 2180, "height": 1320, "alt": "Terento showing a connected Garmin watch and device detection status", "caption": "MTP-based Garmin watches may take 1–2 minutes to appear after connection."}},
            {"title": "Choose a region", "body": "Choose the region you need. Terento shows the download size, current free space and projected storage after installation.", "image": {"asset": "install-maps", "width": 2186, "height": 1318, "alt": "Terento showing map regions and available watch storage", "caption": "Choose a region after Terento has checked the watch and available space."}},
            {"title": "Review and install", "body": "Review the selected maps and storage impact, then start the installation. Keep the watch connected until Terento finishes transferring and verifying the map.", "note": "Terento checks the map source, available storage, completed transfer and final result.", "image": {"asset": "installing-maps", "width": 2176, "height": 1320, "alt": "Terento transferring and verifying a map installation", "caption": "Keep the watch connected until transfer and verification are complete."}},
            {"title": "Check the result", "body": "When Terento reports that the installation is complete, safely eject the watch and confirm that the map is available on the device.", "note": "Map visibility and activity settings may differ by Garmin model. If compatibility sharing is enabled, the result helps confirm compatibility for the exact model and variant."},
        ],
        "troubleshooting": [
            {"title": "Terento does not detect the watch", "body": "Wait up to 1–2 minutes after connecting. If the watch still does not appear, reconnect it, check that the cable supports data and close other Garmin or MTP applications."},
            {"title": "Installation failed", "body": "Open a GitHub issue or email the diagnostic log to hello@terento.app. The log contains the information needed to investigate the failure, so you do not need to inspect device folders manually.", "support_links": True},
            {"title": "Not enough storage", "body": "Choose a smaller region or remove a Terento-managed map you no longer need."},
            {"title": "The map was installed but is not visible", "body": "Reconnect or restart the watch and check its map settings. If the map still does not appear, open an issue or email the diagnostic log to hello@terento.app.", "support_links": True},
        ],

    },
}


TRANSLATIONS = {
    "de": {
        "title": "So installierst du Drittanbieter-Karten auf einer Garmin-Uhr vom Mac aus — Terento",
        "h1": "Drittanbieter-Karten auf einer Garmin-Uhr vom Mac aus installieren",
        "meta_description": "Installiere Drittanbieter-Karten auf einer kompatiblen Garmin-Uhr mit einem Apple-Silicon-Mac und Terento. Verbinde die Uhr, wähle eine Region, prüfe den Speicher und installiere sicher.",
        "eyebrow": "Mac-Installationsanleitung", "intro": "Drittanbieter-Karten auf einer Garmin-Uhr vom Mac aus zu installieren, kann MTP, manuelle Dateiübertragungen oder ältere Desktop-Programme erfordern. Terento bietet einen nativen Ablauf für Apple Silicon: Uhr verbinden, Region wählen, Speicher prüfen und installieren.", "download_beta": "Beta herunterladen", "see_compatibility": "Kompatibilität ansehen", "current_beta": "Die aktuelle Beta verwendet Freizeitkarte", "last_reviewed": "Zuletzt geprüft", "reviewed_date": "28. August 2026", "applies_to": "Gilt für", "skip": "Zum Inhalt springen", "breadcrumb_home": "Startseite", "breadcrumb_current": "Drittanbieter-Karten auf Garmin vom Mac installieren", "before_eyebrow": "Kurz prüfen", "before_title": "Bevor du startest", "checklist": ["Apple-Silicon-Mac", "macOS 13 oder neuer", "Garmin-Smartwatch mit Kartenunterstützung", "USB-Kabel mit Datenübertragung", "Aktuelle Terento-Beta", "Genügend freier Speicher auf der Uhr"], "compatibility_note": "Die Kompatibilitätsseite zeigt genaue Modelle und Varianten mit echten Installationsnachweisen. Sie ist keine vollständige Liste aller Garmin-Uhren, die funktionieren könnten. Nach dem Verbinden prüft Terento das erkannte Gerät und sagt dir, ob die Installation sicher fortgesetzt werden kann.", "steps_eyebrow": "Der Ablauf", "steps_title": "In fünf Schritten installieren", "after_steps_label": "Nächster Schritt", "after_steps_copy": "Die Uhr bleibt geschützt, während Terento Quelle, Speicher, Übertragung und Ergebnis prüft.", "troubleshooting_eyebrow": "Hilfe nötig?", "troubleshooting_title": "Wenn etwas nicht funktioniert", "open_issue": "Issue öffnen", "email_log": "Log per E-Mail senden", "faq_link_eyebrow": "Mehr Hilfe", "faq_link_text": "Noch Fragen?", "faq_link_label": "Die vollständige FAQ ansehen", "bottom_eyebrow": "Bereit, wenn du es bist", "bottom_title": "Installiere die Karte, die du auf deiner Uhr brauchst.",
        "sources": {"eyebrow": "Kurz erklärt", "title": "Warum ein nativer Mac-Ablauf sinnvoll ist", "body": "Garmin beschreibt [BaseCamp] für den Mac derzeit als für Intel-Macs vorgesehen und weist darauf hin, dass Rosetta die Nutzung auf Apple Silicon ermöglichen kann. Für [Garmin Express] gibt Garmin einen ähnlichen Hinweis. Apple erklärt, wie [Rosetta] Intel-Apps auf Apple Silicon ausführt. Terento ist nativ für Apple Silicon und konzentriert sich auf die Installation und Verwaltung von Drittanbieter-Karten.", "limitation": "Terento ersetzt Garmin Express nicht für offizielle Geräteupdates und BaseCamp nicht für weitergehende Routenplanung."},
        "steps": [
            {"title": "Terento herunterladen", "body": "Lade die aktuelle notarielle Beta herunter, öffne die DMG und verschiebe Terento in den Ordner Programme.", "note": "Apple Silicon und macOS 13 oder neuer sind erforderlich."},
            {"title": "Garmin verbinden", "body": "Verbinde die Uhr mit einem USB-Datenkabel. Garmin-Uhren mit MTP können 1–2 Minuten brauchen, bis sie erscheinen. Lass die Uhr verbunden und gib Terento Zeit, die Erkennung abzuschließen.", "note": "Schließe Garmin Express, OpenMTP oder andere Programme, die die Uhr bereits verwenden könnten.", "image": {"asset": "your-garmin", "width": 2180, "height": 1320, "alt": "Terento zeigt eine verbundene Garmin-Uhr und den Gerätestatus", "caption": "Garmin-Uhren mit MTP können nach dem Verbinden 1–2 Minuten brauchen, bis sie erscheinen."}},
            {"title": "Region wählen", "body": "Wähle die benötigte Region. Terento zeigt Downloadgröße, aktuellen freien Speicher und den voraussichtlichen Speicherstand nach der Installation.", "image": {"asset": "install-maps", "width": 2186, "height": 1318, "alt": "Terento zeigt Kartenregionen und verfügbaren Speicher der Uhr", "caption": "Wähle eine Region, nachdem Terento die Uhr und den freien Speicher geprüft hat."}},
            {"title": "Prüfen und installieren", "body": "Prüfe die ausgewählten Karten und die Speicherwirkung und starte dann die Installation. Lass die Uhr verbunden, bis Terento die Karte übertragen und geprüft hat.", "note": "Terento prüft Kartenquelle, verfügbaren Speicher, abgeschlossene Übertragung und Ergebnis.", "image": {"asset": "installing-maps", "width": 2176, "height": 1320, "alt": "Terento überträgt und prüft eine Karteninstallation", "caption": "Lass die Uhr verbunden, bis Übertragung und Prüfung abgeschlossen sind."}},
            {"title": "Ergebnis prüfen", "body": "Wenn Terento die Installation als abgeschlossen meldet, wirf die Uhr sicher aus und prüfe, ob die Karte auf dem Gerät verfügbar ist.", "note": "Kartenanzeige und Aktivitätseinstellungen können je nach Garmin-Modell abweichen. Wenn du Kompatibilitätsdaten teilst, hilft das Ergebnis, die Kompatibilität für genau dieses Modell und diese Variante zu bestätigen."},
        ],
        "troubleshooting": [{"title": "Terento erkennt die Uhr nicht", "body": "Warte nach dem Verbinden bis zu 1–2 Minuten. Wenn die Uhr weiterhin nicht erscheint, verbinde sie erneut, prüfe das Datenkabel und schließe andere Garmin- oder MTP-Programme."}, {"title": "Installation fehlgeschlagen", "body": "Öffne ein GitHub-Issue oder sende das Diagnoseprotokoll per E-Mail an hello@terento.app. Das Protokoll enthält die nötigen Informationen zur Untersuchung. Du musst Geräteordner nicht manuell prüfen.", "support_links": True}, {"title": "Nicht genügend Speicher", "body": "Wähle eine kleinere Region oder entferne eine von Terento verwaltete Karte, die du nicht mehr brauchst."}, {"title": "Die Karte ist installiert, aber nicht sichtbar", "body": "Verbinde die Uhr erneut oder starte sie neu und prüfe die Karteneinstellungen. Wenn die Karte weiterhin nicht erscheint, öffne ein Issue oder sende das Diagnoseprotokoll per E-Mail an hello@terento.app.", "support_links": True}],

    },
    "fr": {
        "title": "Installer des cartes tierces sur une montre Garmin depuis un Mac — Terento", "h1": "Installer des cartes tierces sur une montre Garmin depuis un Mac", "meta_description": "Installez des cartes tierces sur une montre Garmin compatible depuis un Mac Apple Silicon avec Terento. Connectez la montre, choisissez une région, vérifiez le stockage et installez en toute sécurité.", "eyebrow": "Guide d’installation sur Mac", "intro": "Installer des cartes tierces sur une montre Garmin depuis un Mac peut impliquer le MTP, des transferts de fichiers manuels ou d’anciens outils de bureau. Terento propose un parcours natif Apple Silicon : connectez la montre, choisissez une région, vérifiez le stockage et installez.", "download_beta": "Télécharger la bêta", "see_compatibility": "Voir la compatibilité", "current_beta": "La bêta actuelle utilise Freizeitkarte", "last_reviewed": "Dernière vérification", "reviewed_date": "28 août 2026", "applies_to": "S’applique à", "skip": "Aller au contenu", "breadcrumb_home": "Accueil", "breadcrumb_current": "Installer des cartes tierces sur Garmin depuis un Mac", "before_eyebrow": "Vérification rapide", "before_title": "Avant de commencer", "checklist": ["Mac Apple Silicon", "macOS 13 ou version ultérieure", "Montre Garmin compatible avec les cartes", "Câble USB permettant le transfert de données", "Dernière bêta de Terento", "Suffisamment d’espace libre sur la montre"], "compatibility_note": "La page Compatibilité présente les modèles et variantes exacts pour lesquels nous disposons de preuves d’installation réelles. Ce n’est pas la liste complète de toutes les montres Garmin susceptibles de fonctionner. Après la connexion, Terento vérifie l’appareil détecté et vous indique si l’installation peut continuer en toute sécurité.", "steps_eyebrow": "Le parcours", "steps_title": "Installer en cinq étapes", "after_steps_label": "Étape suivante", "after_steps_copy": "La montre reste protégée pendant que Terento vérifie la source, le stockage, le transfert et le résultat.", "troubleshooting_eyebrow": "Besoin d’aide ?", "troubleshooting_title": "Si quelque chose ne fonctionne pas", "open_issue": "Ouvrir une issue", "email_log": "Envoyer le journal", "faq_link_eyebrow": "Plus d’aide", "faq_link_text": "Vous avez encore des questions ?", "faq_link_label": "Voir la FAQ complète", "bottom_eyebrow": "Prêt quand vous l’êtes", "bottom_title": "Installez la carte dont vous avez besoin sur votre montre.",
        "sources": {"eyebrow": "Quelques repères", "title": "Pourquoi un parcours Mac natif est utile", "body": "Garmin indique actuellement que [BaseCamp] pour Mac est destiné aux Mac Intel et que Rosetta peut permettre son utilisation sur Apple Silicon. Garmin donne une indication similaire pour [Garmin Express]. Apple explique comment [Rosetta] permet d’exécuter des apps Intel sur Apple Silicon. Terento est natif pour Apple Silicon et se concentre sur l’installation et la gestion de cartes tierces.", "limitation": "Terento ne remplace pas Garmin Express pour les mises à jour officielles des appareils ni BaseCamp pour les parcours et itinéraires plus larges."},
        "steps": [{"title": "Télécharger Terento", "body": "Téléchargez la dernière bêta notariée, ouvrez le DMG et déplacez Terento dans Applications.", "note": "Apple Silicon et macOS 13 ou version ultérieure sont requis."}, {"title": "Connecter votre Garmin", "body": "Connectez la montre avec un câble USB de données. Les montres Garmin qui utilisent le MTP peuvent mettre 1 à 2 minutes à apparaître. Gardez l’appareil connecté et laissez à Terento le temps de terminer la détection.", "note": "Fermez Garmin Express, OpenMTP ou toute autre app susceptible d’utiliser déjà la montre.", "image": {"asset": "your-garmin", "width": 2180, "height": 1320, "alt": "Terento affiche une montre Garmin connectée et son état de détection", "caption": "Les montres Garmin utilisant le MTP peuvent mettre 1 à 2 minutes à apparaître après la connexion."}}, {"title": "Choisir une région", "body": "Choisissez la région dont vous avez besoin. Terento affiche la taille du téléchargement, l’espace libre actuel et l’espace prévu après l’installation.", "image": {"asset": "install-maps", "width": 2186, "height": 1318, "alt": "Terento affiche des régions cartographiques et l’espace disponible sur la montre", "caption": "Choisissez une région après la vérification de la montre et de l’espace disponible."}}, {"title": "Vérifier et installer", "body": "Vérifiez les cartes sélectionnées et leur impact sur le stockage, puis lancez l’installation. Gardez la montre connectée jusqu’à la fin du transfert et de la vérification par Terento.", "note": "Terento vérifie la source de la carte, l’espace disponible, le transfert terminé et le résultat.", "image": {"asset": "installing-maps", "width": 2176, "height": 1320, "alt": "Terento transfère et vérifie une installation de carte", "caption": "Gardez la montre connectée jusqu’à la fin du transfert et de la vérification."}}, {"title": "Vérifier le résultat", "body": "Lorsque Terento indique que l’installation est terminée, éjectez la montre en toute sécurité et confirmez que la carte est disponible sur l’appareil.", "note": "La visibilité de la carte et les réglages d’activité peuvent varier selon le modèle Garmin. Si le partage de compatibilité est activé, le résultat aide à confirmer la compatibilité du modèle et de la variante exacts."}],
        "troubleshooting": [{"title": "Terento ne détecte pas la montre", "body": "Attendez 1 à 2 minutes après la connexion. Si la montre n’apparaît toujours pas, reconnectez-la, vérifiez que le câble permet les données et fermez les autres apps Garmin ou MTP."}, {"title": "Échec de l’installation", "body": "Ouvrez une issue GitHub ou envoyez le journal de diagnostic à hello@terento.app. Le journal contient les informations nécessaires à l’analyse ; il n’est donc pas nécessaire d’inspecter manuellement les dossiers de l’appareil.", "support_links": True}, {"title": "Espace de stockage insuffisant", "body": "Choisissez une région plus petite ou supprimez une carte gérée par Terento dont vous n’avez plus besoin."}, {"title": "La carte est installée mais n’est pas visible", "body": "Reconnectez ou redémarrez la montre et vérifiez ses réglages de carte. Si la carte n’apparaît toujours pas, ouvrez une issue ou envoyez le journal de diagnostic à hello@terento.app.", "support_links": True}],

    },
    "pl": {
        "title": "Jak instalować mapy innych firm na zegarku Garmin z Maca — Terento", "h1": "Jak instalować mapy innych firm na zegarku Garmin z Maca", "meta_description": "Instaluj mapy innych firm na zgodnym zegarku Garmin z Maca z Apple Silicon za pomocą Terento. Podłącz zegarek, wybierz region, sprawdź pamięć i bezpiecznie zainstaluj mapę.", "eyebrow": "Instrukcja instalacji na Macu", "intro": "Instalowanie map innych firm na zegarku Garmin z Maca może wymagać MTP, ręcznego przesyłania plików lub starszych programów komputerowych. Terento oferuje natywny dla Apple Silicon sposób: podłącz zegarek, wybierz region, sprawdź pamięć i zainstaluj.", "download_beta": "Pobierz betę", "see_compatibility": "Zobacz kompatybilność", "current_beta": "Obecna beta korzysta z Freizeitkarte", "last_reviewed": "Ostatni przegląd", "reviewed_date": "28 sierpnia 2026", "applies_to": "Dotyczy", "skip": "Przejdź do treści", "breadcrumb_home": "Strona główna", "breadcrumb_current": "Instalowanie map innych firm na Garminie z Maca", "before_eyebrow": "Szybka kontrola", "before_title": "Zanim zaczniesz", "checklist": ["Mac z Apple Silicon", "macOS 13 lub nowszy", "Zegarek Garmin z obsługą map", "Kabel USB obsługujący przesyłanie danych", "Najnowsza beta Terento", "Wystarczająca ilość wolnego miejsca na zegarku"], "compatibility_note": "Strona kompatybilności pokazuje konkretne modele i warianty z rzeczywistymi dowodami instalacji. Nie jest pełną listą wszystkich zegarków Garmin, które mogą działać. Po podłączeniu Terento sprawdzi wykryte urządzenie i powie, czy instalację można bezpiecznie kontynuować.", "steps_eyebrow": "Przebieg instalacji", "steps_title": "Zainstaluj w pięciu krokach", "after_steps_label": "Następny krok", "after_steps_copy": "Zegarek pozostaje chroniony, gdy Terento sprawdza źródło, pamięć, przesyłanie i wynik.", "troubleshooting_eyebrow": "Potrzebujesz pomocy?", "troubleshooting_title": "Jeśli coś nie działa", "open_issue": "Otwórz zgłoszenie", "email_log": "Wyślij log e-mailem", "faq_link_eyebrow": "Więcej pomocy", "faq_link_text": "Masz jeszcze pytania?", "faq_link_label": "Zobacz pełne FAQ", "bottom_eyebrow": "Gotowe, gdy Ty będziesz", "bottom_title": "Zainstaluj na zegarku mapę, której potrzebujesz.",
        "sources": {"eyebrow": "Kilka informacji", "title": "Dlaczego natywna obsługa Maca ma znaczenie", "body": "Garmin informuje obecnie, że [BaseCamp] na Maca jest przeznaczony dla komputerów z procesorem Intel, a Rosetta może umożliwić jego użycie na Apple Silicon. Podobną informację Garmin podaje dla [Garmin Express]. Apple wyjaśnia, jak [Rosetta] uruchamia aplikacje Intel na Apple Silicon. Terento jest natywne dla Apple Silicon i skupia się konkretnie na instalowaniu i zarządzaniu mapami innych firm.", "limitation": "Terento nie zastępuje Garmin Express w zakresie oficjalnych aktualizacji urządzenia ani BaseCamp w szerszym planowaniu tras."},
        "steps": [{"title": "Pobierz Terento", "body": "Pobierz najnowszą notaryzowaną betę, otwórz DMG i przenieś Terento do folderu Programy.", "note": "Wymagane są Apple Silicon i macOS 13 lub nowszy."}, {"title": "Podłącz Garmina", "body": "Podłącz zegarek kablem USB do transmisji danych. Zegarki Garmin korzystające z MTP mogą pojawić się dopiero po 1–2 minutach. Pozostaw urządzenie podłączone i daj Terento czas na zakończenie wykrywania.", "note": "Zamknij Garmin Express, OpenMTP i inne aplikacje, które mogą już korzystać z zegarka.", "image": {"asset": "your-garmin", "width": 2180, "height": 1320, "alt": "Terento pokazuje podłączony zegarek Garmin i stan wykrywania", "caption": "Zegarki Garmin korzystające z MTP mogą pojawić się 1–2 minuty po podłączeniu."}}, {"title": "Wybierz region", "body": "Wybierz potrzebny region. Terento pokazuje rozmiar pobierania, aktualną ilość wolnego miejsca i przewidywaną ilość pamięci po instalacji.", "image": {"asset": "install-maps", "width": 2186, "height": 1318, "alt": "Terento pokazuje regiony map i wolne miejsce na zegarku", "caption": "Wybierz region, gdy Terento sprawdzi zegarek i dostępną pamięć."}}, {"title": "Sprawdź i zainstaluj", "body": "Sprawdź wybrane mapy i wpływ na pamięć, a następnie rozpocznij instalację. Pozostaw zegarek podłączony, aż Terento zakończy przesyłanie i weryfikację mapy.", "note": "Terento sprawdza źródło mapy, dostępną pamięć, ukończone przesyłanie i końcowy wynik.", "image": {"asset": "installing-maps", "width": 2176, "height": 1320, "alt": "Terento przesyła i weryfikuje instalację mapy", "caption": "Pozostaw zegarek podłączony do zakończenia przesyłania i weryfikacji."}}, {"title": "Sprawdź wynik", "body": "Gdy Terento poinformuje o ukończeniu instalacji, bezpiecznie odłącz zegarek i sprawdź, czy mapa jest dostępna na urządzeniu.", "note": "Widoczność map i ustawienia aktywności mogą różnić się zależnie od modelu Garmin. Jeśli udostępnianie danych o kompatybilności jest włączone, wynik pomaga potwierdzić kompatybilność konkretnego modelu i wariantu."}],
        "troubleshooting": [{"title": "Terento nie wykrywa zegarka", "body": "Odczekaj 1–2 minuty po podłączeniu. Jeśli zegarek nadal się nie pojawia, podłącz go ponownie, sprawdź, czy kabel przesyła dane, i zamknij inne aplikacje Garmin lub MTP."}, {"title": "Instalacja nie powiodła się", "body": "Otwórz zgłoszenie na GitHubie albo wyślij log diagnostyczny na adres hello@terento.app. Log zawiera informacje potrzebne do zbadania problemu, więc nie musisz ręcznie przeglądać folderów urządzenia.", "support_links": True}, {"title": "Za mało miejsca", "body": "Wybierz mniejszy region albo usuń zarządzaną przez Terento mapę, której już nie potrzebujesz."}, {"title": "Mapa została zainstalowana, ale jej nie widać", "body": "Podłącz zegarek ponownie lub uruchom go ponownie i sprawdź ustawienia map. Jeśli mapa nadal się nie pojawia, otwórz zgłoszenie albo wyślij log diagnostyczny na adres hello@terento.app.", "support_links": True}],

    },
    "cs": {
        "title": "Jak nainstalovat mapy třetích stran do hodinek Garmin z Macu — Terento", "h1": "Jak nainstalovat mapy třetích stran do hodinek Garmin z Macu", "meta_description": "Nainstalujte mapy třetích stran do kompatibilních hodinek Garmin z Macu s Apple Silicon pomocí Terento. Připojte hodinky, vyberte region, zkontrolujte úložiště a bezpečně instalujte.", "eyebrow": "Průvodce instalací na Macu", "intro": "Instalace map třetích stran do hodinek Garmin z Macu může vyžadovat MTP, ruční přenos souborů nebo starší desktopové nástroje. Terento nabízí nativní postup pro Apple Silicon: připojte hodinky, vyberte region, zkontrolujte úložiště a instalujte.", "download_beta": "Stáhnout betu", "see_compatibility": "Zobrazit kompatibilitu", "current_beta": "Aktuální beta používá Freizeitkarte", "last_reviewed": "Naposledy ověřeno", "reviewed_date": "28. srpna 2026", "applies_to": "Platí pro", "skip": "Přejít k obsahu", "breadcrumb_home": "Domů", "breadcrumb_current": "Instalace map třetích stran do Garminu z Macu", "before_eyebrow": "Rychlá kontrola", "before_title": "Než začnete", "checklist": ["Mac s Apple Silicon", "macOS 13 nebo novější", "Hodinky Garmin s podporou map", "USB kabel s podporou přenosu dat", "Nejnovější beta Terento", "Dostatek volného místa v hodinkách"], "compatibility_note": "Stránka Kompatibilita zobrazuje přesné modely a varianty s reálnými doklady instalace. Nejde o úplný seznam všech hodinek Garmin, které mohou fungovat. Po připojení Terento zkontroluje rozpoznané zařízení a řekne vám, zda lze bezpečně pokračovat v instalaci.", "steps_eyebrow": "Postup", "steps_title": "Instalace v pěti krocích", "after_steps_label": "Další krok", "after_steps_copy": "Hodinky zůstanou chráněné, zatímco Terento ověří zdroj, úložiště, přenos a výsledek.", "troubleshooting_eyebrow": "Potřebujete pomoc?", "troubleshooting_title": "Když něco nefunguje", "open_issue": "Otevřít issue", "email_log": "Poslat log e-mailem", "faq_link_eyebrow": "Další pomoc", "faq_link_text": "Máte ještě otázky?", "faq_link_label": "Zobrazit celé FAQ", "bottom_eyebrow": "Připraveno, až budete vy", "bottom_title": "Dostaňte do hodinek mapu, kterou potřebujete.",
        "sources": {"eyebrow": "Stručný kontext", "title": "Proč záleží na nativním postupu pro Mac", "body": "Garmin v současnosti uvádí, že [BaseCamp] pro Mac je určen pro Macy s procesorem Intel a že Rosetta může umožnit jeho používání na Apple Silicon. Podobné doporučení Garmin uvádí pro [Garmin Express]. Apple vysvětluje, jak [Rosetta] spouští aplikace pro Intel na Apple Silicon. Terento je nativní pro Apple Silicon a zaměřuje se konkrétně na instalaci a správu map třetích stran.", "limitation": "Terento nenahrazuje Garmin Express pro oficiální aktualizace zařízení ani BaseCamp pro širší plánování tras."},
        "steps": [{"title": "Stáhněte Terento", "body": "Stáhněte nejnovější notářsky ověřenou betu, otevřete DMG a přesuňte Terento do složky Aplikace.", "note": "Je vyžadován Apple Silicon a macOS 13 nebo novější."}, {"title": "Připojte Garmin", "body": "Připojte hodinky datovým USB kabelem. Hodinky Garmin používající MTP se mohou zobrazit až za 1–2 minuty. Nechte zařízení připojené a dejte Terento čas dokončit rozpoznání.", "note": "Ukončete Garmin Express, OpenMTP nebo jinou aplikaci, která může hodinky právě používat.", "image": {"asset": "your-garmin", "width": 2180, "height": 1320, "alt": "Terento zobrazuje připojené hodinky Garmin a stav rozpoznání", "caption": "Hodinky Garmin s MTP se po připojení mohou zobrazit až za 1–2 minuty."}}, {"title": "Vyberte region", "body": "Vyberte potřebný region. Terento zobrazí velikost stahování, aktuální volné místo a odhad úložiště po instalaci.", "image": {"asset": "install-maps", "width": 2186, "height": 1318, "alt": "Terento zobrazuje regiony map a volné místo v hodinkách", "caption": "Region vyberte až poté, co Terento zkontroluje hodinky a volné místo."}}, {"title": "Zkontrolujte a nainstalujte", "body": "Zkontrolujte vybrané mapy a dopad na úložiště a poté spusťte instalaci. Nechte hodinky připojené, dokud Terento nedokončí přenos a ověření mapy.", "note": "Terento kontroluje zdroj mapy, dostupné úložiště, dokončený přenos a konečný výsledek.", "image": {"asset": "installing-maps", "width": 2176, "height": 1320, "alt": "Terento přenáší a ověřuje instalaci mapy", "caption": "Hodinky neodpojujte, dokud nebude přenos a ověření dokončeno."}}, {"title": "Zkontrolujte výsledek", "body": "Až Terento oznámí dokončení instalace, hodinky bezpečně vysuňte a ověřte, že je mapa v zařízení dostupná.", "note": "Viditelnost map a nastavení aktivit se mohou podle modelu Garmin lišit. Pokud je zapnuté sdílení kompatibility, výsledek pomůže potvrdit kompatibilitu přesného modelu a varianty."}],
        "troubleshooting": [{"title": "Terento hodinky nerozpozná", "body": "Po připojení počkejte 1–2 minuty. Pokud se hodinky stále nezobrazí, připojte je znovu, ověřte, že kabel přenáší data, a ukončete ostatní aplikace Garmin nebo MTP."}, {"title": "Instalace se nezdařila", "body": "Otevřete issue na GitHubu nebo pošlete diagnostický log na hello@terento.app. Log obsahuje informace potřebné k prošetření, takže nemusíte ručně procházet složky zařízení.", "support_links": True}, {"title": "Nedostatek úložiště", "body": "Vyberte menší region nebo odstraňte mapu spravovanou Terento, kterou už nepotřebujete."}, {"title": "Mapa je nainstalovaná, ale není vidět", "body": "Hodinky znovu připojte nebo restartujte a zkontrolujte jejich nastavení map. Pokud se mapa stále nezobrazuje, otevřete issue nebo pošlete diagnostický log na hello@terento.app.", "support_links": True}],

    },
    "it": {
        "title": "Come installare mappe di terze parti su uno smartwatch Garmin da Mac — Terento", "h1": "Come installare mappe di terze parti su uno smartwatch Garmin da Mac", "meta_description": "Installa mappe di terze parti su uno smartwatch Garmin compatibile da un Mac Apple Silicon con Terento. Collega l’orologio, scegli una regione, controlla lo spazio e installa in sicurezza.", "eyebrow": "Guida all’installazione su Mac", "intro": "Installare mappe di terze parti su uno smartwatch Garmin da Mac può richiedere MTP, trasferimenti manuali dei file o strumenti desktop meno recenti. Terento offre un flusso nativo per Apple Silicon: collega l’orologio, scegli una regione, controlla lo spazio e installa.", "download_beta": "Scarica la beta", "see_compatibility": "Vedi la compatibilità", "current_beta": "La beta attuale usa Freizeitkarte", "last_reviewed": "Ultima verifica", "reviewed_date": "28 agosto 2026", "applies_to": "Si applica a", "skip": "Vai al contenuto", "breadcrumb_home": "Home", "breadcrumb_current": "Installare mappe di terze parti su Garmin da Mac", "before_eyebrow": "Un controllo rapido", "before_title": "Prima di iniziare", "checklist": ["Mac Apple Silicon", "macOS 13 o versioni successive", "Smartwatch Garmin con supporto alle mappe", "Cavo USB che supporti il trasferimento dati", "Ultima beta di Terento", "Spazio libero sufficiente sull’orologio"], "compatibility_note": "La pagina Compatibilità mostra modelli e varianti esatti con prove reali di installazione. Non è un elenco completo di tutti gli orologi Garmin che potrebbero funzionare. Dopo il collegamento, Terento controlla il dispositivo rilevato e ti dice se puoi continuare l’installazione in sicurezza.", "steps_eyebrow": "Il flusso", "steps_title": "Installa in cinque passaggi", "after_steps_label": "Passaggio successivo", "after_steps_copy": "L’orologio resta protetto mentre Terento controlla la fonte, lo spazio, il trasferimento e il risultato.", "troubleshooting_eyebrow": "Serve aiuto?", "troubleshooting_title": "Se qualcosa non funziona", "open_issue": "Apri una issue", "email_log": "Invia il log", "faq_link_eyebrow": "Altra assistenza", "faq_link_text": "Hai ancora domande?", "faq_link_label": "Vedi le FAQ completa", "bottom_eyebrow": "Pronto quando vuoi", "bottom_title": "Installa sul tuo orologio la mappa di cui hai bisogno.",
        "sources": {"eyebrow": "Un po’ di contesto", "title": "Perché è utile un flusso Mac nativo", "body": "Garmin indica attualmente che [BaseCamp] per Mac è destinato ai Mac con processore Intel e che Rosetta può consentirne l’uso su Apple Silicon. Garmin dà indicazioni simili per [Garmin Express]. Apple spiega come [Rosetta] permette di eseguire app Intel su Apple Silicon. Terento è nativo per Apple Silicon e si concentra sull’installazione e la gestione di mappe di terze parti.", "limitation": "Terento non sostituisce Garmin Express per gli aggiornamenti ufficiali dei dispositivi né BaseCamp per i flussi più ampi di pianificazione dei percorsi."},
        "steps": [{"title": "Scarica Terento", "body": "Scarica l’ultima beta notarizzata, apri il DMG e sposta Terento nella cartella Applicazioni.", "note": "Sono richiesti Apple Silicon e macOS 13 o versioni successive."}, {"title": "Collega il tuo Garmin", "body": "Collega lo smartwatch con un cavo USB dati. Gli orologi Garmin che usano MTP possono impiegare 1–2 minuti per apparire. Lascia il dispositivo collegato e dai a Terento il tempo di completare il rilevamento.", "note": "Chiudi Garmin Express, OpenMTP o altre app che potrebbero già usare l’orologio.", "image": {"asset": "your-garmin", "width": 2180, "height": 1320, "alt": "Terento mostra uno smartwatch Garmin collegato e lo stato del rilevamento", "caption": "Gli smartwatch Garmin basati su MTP possono impiegare 1–2 minuti per apparire dopo il collegamento."}}, {"title": "Scegli una regione", "body": "Scegli la regione che ti serve. Terento mostra la dimensione del download, lo spazio libero attuale e lo spazio previsto dopo l’installazione.", "image": {"asset": "install-maps", "width": 2186, "height": 1318, "alt": "Terento mostra le regioni della mappa e lo spazio disponibile sull’orologio", "caption": "Scegli una regione dopo che Terento ha controllato l’orologio e lo spazio disponibile."}}, {"title": "Controlla e installa", "body": "Controlla le mappe selezionate e l’impatto sullo spazio, poi avvia l’installazione. Lascia l’orologio collegato finché Terento non termina il trasferimento e la verifica della mappa.", "note": "Terento controlla la fonte della mappa, lo spazio disponibile, il trasferimento completato e il risultato finale.", "image": {"asset": "installing-maps", "width": 2176, "height": 1320, "alt": "Terento trasferisce e verifica un’installazione della mappa", "caption": "Lascia l’orologio collegato fino al completamento del trasferimento e della verifica."}}, {"title": "Controlla il risultato", "body": "Quando Terento segnala che l’installazione è completa, espelli l’orologio in modo sicuro e verifica che la mappa sia disponibile sul dispositivo.", "note": "La visibilità della mappa e le impostazioni delle attività possono variare in base al modello Garmin. Se la condivisione della compatibilità è attiva, il risultato aiuta a confermare la compatibilità del modello e della variante esatti."}],
        "troubleshooting": [{"title": "Terento non rileva l’orologio", "body": "Attendi 1–2 minuti dopo il collegamento. Se l’orologio non appare ancora, ricollegalo, controlla che il cavo supporti i dati e chiudi le altre app Garmin o MTP."}, {"title": "Installazione non riuscita", "body": "Apri una issue su GitHub oppure invia il log diagnostico a hello@terento.app. Il log contiene le informazioni necessarie per l’analisi, quindi non devi controllare manualmente le cartelle del dispositivo.", "support_links": True}, {"title": "Spazio insufficiente", "body": "Scegli una regione più piccola oppure rimuovi una mappa gestita da Terento che non ti serve più."}, {"title": "La mappa è installata ma non è visibile", "body": "Ricollega o riavvia l’orologio e controlla le impostazioni della mappa. Se la mappa non appare ancora, apri una issue oppure invia il log diagnostico a hello@terento.app.", "support_links": True}],

    },
}


def merged_copy(locale: str) -> dict[str, object]:
    if locale == "en":
        return COMMON["en"]
    base = COMMON["en"].copy()
    base.update(TRANSLATIONS[locale])
    base["see_compatibility_evidence"] = {
        "de": "Aktuelle Kompatibilitätsnachweise ansehen",
        "fr": "Voir les preuves actuelles de compatibilité",
        "pl": "Zobacz aktualne dowody kompatybilności",
        "cs": "Zobrazit aktuální doklady kompatibility",
        "it": "Vedi le prove attuali di compatibilità",
    }[locale]
    return base


def main() -> None:
    release_path = ROOT / "site" / "updates" / "macos-arm64.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    for locale in ("en", "de", "fr", "pl", "cs", "it"):
        output = ROOT / "site" / localized_path(locale, GUIDE_SLUG).lstrip("/") / "index.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        rendered = render(locale, merged_copy(locale), release)
        output.write_text(re.sub(r"[ \t]+\n", "\n", rendered), encoding="utf-8")
        print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
