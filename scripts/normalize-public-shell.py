#!/usr/bin/env python3
"""Synchronize static fallback headers and footers with site-shell.js."""

from __future__ import annotations

import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL_VERSION = "20260904-language-selector"
STYLE_VERSION = "20260904-language-selector"
IMAGE_VERSION = "20260902-your-garmin"
LANGUAGE_VERSION = "20260904-language-selector"
LOCALIZED_CONTENT_VERSION = "20260904-download-page-cards"
COMPATIBILITY_LOCALES_VERSION = "20260904-beta-provider-scope"
COMPATIBILITY_VERSION = "20260904-snapshot"
UMAMI_SCRIPT_VERSION = "20260904-public-link-events"
LOCALES = {
    "en": {"flag": "🇬🇧", "name": "English", "home": "Terento home", "primary": "Primary navigation", "menu": "Menu", "close": "Close menu", "about": "About", "compatibility": "Compatibility", "guide": "Guide", "faq": "FAQ", "download": "Download", "language": "Choose language", "footer": "Footer navigation", "status": "Open-source project", "legal": "Legal", "privacy": "Privacy", "support": "Support Terento", "stats": "Visit statistics (Umami) do not use cookies."},
    "de": {"flag": "🇩🇪", "name": "Deutsch", "home": "Terento Startseite", "primary": "Hauptnavigation", "menu": "Menü", "close": "Menü schließen", "about": "Über uns", "compatibility": "Kompatibilität", "guide": "Anleitung", "faq": "FAQ", "download": "Download", "language": "Sprache wählen", "footer": "Footer-Navigation", "status": "Open-Source-Projekt", "legal": "Rechtliches", "privacy": "Datenschutz", "support": "Support Terento", "stats": "Besuchsstatistik (Umami) verwendet keine Cookies."},
    "fr": {"flag": "🇫🇷", "name": "Français", "home": "Accueil Terento", "primary": "Navigation principale", "menu": "Menu", "close": "Fermer le menu", "about": "À propos", "compatibility": "Compatibilité", "guide": "Guide", "faq": "FAQ", "download": "Télécharger", "language": "Choisir la langue", "footer": "Navigation du pied de page", "status": "Projet open source", "legal": "Mentions légales", "privacy": "Confidentialité", "support": "Support Terento", "stats": "Les statistiques de visites (Umami) n’utilisent pas de cookies."},
    "pl": {"flag": "🇵🇱", "name": "Polski", "home": "Strona główna Terento", "primary": "Główna nawigacja", "menu": "Menu", "close": "Zamknij menu", "about": "O projekcie", "compatibility": "Kompatybilność", "guide": "Poradnik", "faq": "FAQ", "download": "Pobierz", "language": "Wybierz język", "footer": "Nawigacja w stopce", "status": "Projekt open source", "legal": "Informacje prawne", "privacy": "Prywatność", "support": "Support Terento", "stats": "Statystyki odwiedzin (Umami) nie używają plików cookie."},
    "cs": {"flag": "🇨🇿", "name": "Čeština", "home": "Domů Terento", "primary": "Hlavní navigace", "menu": "Menu", "close": "Zavřít menu", "about": "O projektu", "compatibility": "Kompatibilita", "guide": "Průvodce", "faq": "FAQ", "download": "Stáhnout", "language": "Vybrat jazyk", "footer": "Navigace v zápatí", "status": "Open-source projekt", "legal": "Právní informace", "privacy": "Soukromí", "support": "Support Terento", "stats": "Statistiky návštěvnosti (Umami) nepoužívají cookies."},
    "it": {"flag": "🇮🇹", "name": "Italiano", "home": "Home Terento", "primary": "Navigazione principale", "menu": "Menu", "close": "Chiudi menu", "about": "Informazioni", "compatibility": "Compatibilità", "guide": "Guida", "faq": "FAQ", "download": "Scarica", "language": "Scegli la lingua", "footer": "Navigazione del piè di pagina", "status": "Progetto open source", "legal": "Note legali", "privacy": "Privacy", "support": "Support Terento", "stats": "Le statistiche delle visite (Umami) non usano cookie."},
}


def localized_root(locale: str) -> str:
    return "/" if locale == "en" else f"/{locale}/"


def route_for(locale: str, route: str) -> str:
    return f"{localized_root(locale)}{route}"


def language_links(locale: str, route: str) -> str:
    links = []
    for candidate, candidate_copy in LOCALES.items():
        href = route_for(candidate, route)
        current = ' aria-current="page"' if candidate == locale else ""
        links.append(f'<a class="language-option" href="{href}" data-language-switch="{candidate}" lang="{candidate}" aria-label="{candidate_copy["name"]}"{current}><span class="language-option-flag" aria-hidden="true">{candidate_copy["flag"]}</span><span>{candidate_copy["name"]}</span></a>')
    return "".join(links)


def shell(locale: str, route: str, page: str) -> tuple[str, str]:
    copy = LOCALES[locale]
    root = localized_root(locale)
    compatibility = route_for(locale, "compatibility/")
    download = route_for(locale, "download/")
    guide = route_for(locale, "guides/install-garmin-maps-mac/")
    route_for_language = route if page in {"about", "compatibility", "download", "guide"} else ""
    nav = {"about": route_for(locale, "about/"), "compatibility": compatibility, "guide": guide, "faq": f"{root}#faq", "download": download}
    active = {"about": page == "about", "compatibility": page == "compatibility", "guide": page == "guide", "download": page == "download"}
    def nav_link(key: str, variant: str = "") -> str:
        current = ' aria-current="page"' if active.get(key) else ""
        class_attribute = f' class="{variant}"' if variant else ""
        return f'<a{class_attribute} href="{nav[key]}"{current}>{copy[key]}</a>'
    language_menu = f'''<details class="language-menu">
          <summary class="language-trigger" aria-label="{copy["language"]}"><span class="language-code" aria-hidden="true">{locale.upper()}</span></summary>
          <div class="language-options">{language_links(locale, route_for_language)}</div>
        </details>'''
    header = f'''<header class="site-header">
      <div class="shell header-inner">
        <a class="brand-lockup" href="{root}" aria-label="{copy["home"]}">
          <img src="/assets/logo-sky.svg" alt="" width="40" height="40">
          <span>Terento</span>
        </a>
        <nav class="primary-nav" aria-label="{copy["primary"]}">
          {nav_link("compatibility")}{nav_link("guide")}{nav_link("about")}{nav_link("download", "download-action")}
          <span class="language-switcher">{language_menu}</span>
        </nav>
        <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="mobile-nav" aria-label="{copy["menu"]}">
          <span class="menu-toggle-icon" aria-hidden="true"><span></span><span></span><span></span></span>
          <span class="menu-toggle-text">{copy["menu"]}</span>
        </button>
      </div>
      <div class="mobile-nav" id="mobile-nav" hidden>
        <div class="shell mobile-nav-inner">
          <nav class="mobile-nav-links" aria-label="{copy["primary"]}">
            {nav_link("compatibility")}{nav_link("guide")}{nav_link("about")}{nav_link("download", "download-action")}
          </nav>
          <div class="mobile-nav-language"><details class="language-menu mobile-language-menu">
            <summary class="language-trigger" aria-label="{copy["language"]}"><span class="mobile-language-label">{locale.upper()}</span></summary>
            <div class="language-options">{language_links(locale, route_for_language)}</div>
          </details></div>
        </div>
      </div>
    </header>'''
    footer = f'''<footer class="site-footer">
      <div class="shell footer-grid">
        <div class="footer-identity">
          <a class="brand-lockup footer-brand" href="{root}" aria-label="{copy["home"]}">
            <img src="/assets/logo-white.svg" alt="" width="32" height="32">
            <span>Terento</span>
          </a>
          <div class="footer-meta"><a class="footer-status footer-project-link" data-project-link href="https://github.com/VooZ2/terento" target="_blank" rel="noopener noreferrer">{copy["status"]}</a><a class="footer-support-link" data-support-link href="https://buymeacoffee.com/vooz2" rel="noopener noreferrer">{copy["support"]}</a></div>
        </div>
        <nav class="footer-nav" aria-label="{copy["footer"]}">
          {nav_link("about")}{nav_link("compatibility")}{nav_link("guide")}{nav_link("faq")}{nav_link("download")}
          <a href="/legal/">{copy["legal"]}</a>
          <a href="/privacy/">{copy["privacy"]}</a>
        </nav>
      </div>
      <div class="shell footer-bottom"><p>© 2026 Terento Project · Beta</p></div>
      <div class="shell footer-note"><p>{copy["stats"]}</p></div>
    </footer>'''
    return header, footer


def files() -> list[tuple[str, str, str]]:
    result = []
    for locale in LOCALES:
        prefix = "" if locale == "en" else f"{locale}/"
        result.extend([
            (f"site/{prefix}index.html", locale, "home"),
            (f"site/{prefix}about/index.html", locale, "about"),
            (f"site/{prefix}download/index.html", locale, "download"),
            (f"site/{prefix}compatibility/index.html", locale, "compatibility"),
            (f"site/{prefix}guides/install-garmin-maps-mac/index.html", locale, "guide"),
        ])
    result.extend([("site/legal/index.html", "en", "legal"), ("site/privacy/index.html", "en", "privacy")])
    return result


def main() -> None:
    for relative, locale, page in files():
        path = ROOT / relative
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        header, footer = shell(locale, "about/" if page == "about" else "compatibility/" if page == "compatibility" else "download/" if page == "download" else "guides/install-garmin-maps-mac/" if page == "guide" else "", page)
        source, header_count = re.subn(r'<header class="site-header">[\s\S]*?</header>', header, source, count=1)
        if not header_count:
            raise SystemExit(f"missing header in {relative}")
        source, footer_count = re.subn(r'<footer class="site-footer">[\s\S]*?</footer>', footer, source, count=1)
        if not footer_count:
            raise SystemExit(f"missing footer in {relative}")
        source = re.sub(r'(/site-shell\.js\?v=)[^"\s]+', rf'\g<1>{SHELL_VERSION}', source)
        source = re.sub(r'\s*<meta name="theme-color" media="\(prefers-color-scheme: dark\)"[^>]*>', '', source)
        source = re.sub(
            r'(<meta name="theme-color" content="#F7F3EC">)',
            r'\1\n    <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#222A2B">',
            source,
            count=1,
        )
        source = re.sub(r'\s*<link rel="stylesheet" href="/styles\.css\?v=[^"\s]+">', "", source)
        source, style_anchor_count = re.subn(
            r'(<script defer src="/site-shell\.js\?v=[^"\s]+"></script>)',
            rf'\1\n    <link rel="stylesheet" href="/styles.css?v={STYLE_VERSION}">',
            source,
            count=1,
        )
        if style_anchor_count != 1:
            raise SystemExit(f"missing site-shell script before stylesheet in {relative}")
        source = re.sub(
            r'(/assets/app/optimized/your-garmin-\d+\.(?:avif|webp|png))(?!\?v=)[^"\s]*',
            rf'\1?v={IMAGE_VERSION}',
            source,
        )
        source = source.replace('width="2205" height="1348"', 'width="2200" height="1346"')
        source = re.sub(
            r'(/localized-content\.js\?v=)[^"\s]+',
            rf'\g<1>{LOCALIZED_CONTENT_VERSION}',
            source,
        )
        source = re.sub(r'(/language\.js\?v=)[^"\s]+', rf'\g<1>{LANGUAGE_VERSION}', source)
        source = re.sub(r'(/privacy-consent\.js\?v=)[^"\s]+', rf'\g<1>{UMAMI_SCRIPT_VERSION}', source)
        source = re.sub(
            r'(<script defer src="/privacy-consent\.js\?v=[^"\s]+"></script>)(?:\s*\1)+',
            r'\1',
            source,
        )
        if page == "compatibility":
            source = re.sub(r'(/compatibility/compatibility-locales\.js\?v=)[^"\s]+', rf'\g<1>{COMPATIBILITY_LOCALES_VERSION}', source)
            source = re.sub(r'(/compatibility/compatibility\.js\?v=)[^"\s]+', rf'\g<1>{COMPATIBILITY_VERSION}', source)
        path.write_text(source, encoding="utf-8")
    print("Synchronized static public headers and footers.")


if __name__ == "__main__":
    main()
