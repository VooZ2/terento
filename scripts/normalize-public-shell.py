#!/usr/bin/env python3
"""Generate the shared public headers, footers and in-page language copy."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL_VERSION = "20261105-copy-command-v1"
PROVIDER_SCRIPT_VERSION = "20261026-osmapa-v1"
STYLE_VERSION = "20261106-audit-fixes-v1"
IMAGE_VERSION = "20260912-app-screens-v2"
LANGUAGE_VERSION = "20260926-static-shell-v1"
COMPATIBILITY_LOCALES_VERSION = "20261106-compatibility-title-v1"
COMPATIBILITY_VERSION = "20261105-compatibility-clear-v2"
UMAMI_SCRIPT_VERSION = "20261113-umami-cleanup"
PAGE_LANGUAGE_VERSION = "20261015-shared-page-language-v3"
# Footer Web installer link: the public installer (launch 2026-10-29) on the
# site's language paths; site-shell.js follows a language switch on Legal/Privacy.
WEB_INSTALLER_URL = "/install/"
LOCALES = {
    "en": {"flag": "🇬🇧", "name": "English", "home": "Terento home", "primary": "Primary navigation", "menu": "Menu", "close": "Close menu", "about": "About", "styles": "Maps", "compatibility": "Compatibility", "guide": "Guide", "faq": "FAQ", "troubleshooting": "Troubleshooting", "download": "Download", "language": "Choose language", "footer": "Footer navigation", "status": "Source code", "legal": "Legal", "privacy": "Privacy", "support": "Donate", "web_installer": "Web installer", "support_via": "Buy Me a Coffee", "tagline": "Free maps for your Garmin watch or Edge.", "col_install": "Install", "col_help": "Help", "col_project": "Project", "guide_watch": "Watch guide", "guide_edge": "Edge guide", "guide_linux": "Linux guide"},
    "de": {"flag": "🇩🇪", "name": "Deutsch", "home": "Terento Startseite", "primary": "Hauptnavigation", "menu": "Menü", "close": "Menü schließen", "about": "Über uns", "styles": "Karten", "compatibility": "Kompatibilität", "guide": "Anleitung", "faq": "FAQ", "troubleshooting": "Fehlerbehebung", "download": "Download", "language": "Sprache wählen", "footer": "Footer-Navigation", "status": "Quellcode", "legal": "Rechtliches", "privacy": "Datenschutz", "support": "Spenden", "web_installer": "Web-Installer", "support_via": "Buy Me a Coffee", "tagline": "Kostenlose Karten für deine Garmin-Uhr oder deinen Edge.", "col_install": "Installieren", "col_help": "Hilfe", "col_project": "Projekt", "guide_watch": "Anleitung für Uhren", "guide_edge": "Anleitung für Edge", "guide_linux": "Anleitung für Linux"},
    "fr": {"flag": "🇫🇷", "name": "Français", "home": "Accueil Terento", "primary": "Navigation principale", "menu": "Menu", "close": "Fermer le menu", "about": "À propos", "styles": "Cartes", "compatibility": "Compatibilité", "guide": "Guide", "faq": "FAQ", "troubleshooting": "Dépannage", "download": "Télécharger", "language": "Choisir la langue", "footer": "Navigation du pied de page", "status": "Code source", "legal": "Mentions légales", "privacy": "Confidentialité", "support": "Faire un don", "web_installer": "Installateur web", "support_via": "Buy Me a Coffee", "tagline": "Cartes gratuites pour votre montre Garmin ou votre Edge.", "col_install": "Installer", "col_help": "Aide", "col_project": "Projet", "guide_watch": "Guide montre", "guide_edge": "Guide Edge", "guide_linux": "Guide Linux"},
    "pl": {"flag": "🇵🇱", "name": "Polski", "home": "Strona główna Terento", "primary": "Główna nawigacja", "menu": "Menu", "close": "Zamknij menu", "about": "O projekcie", "styles": "Mapy", "compatibility": "Kompatybilność", "guide": "Poradnik", "faq": "FAQ", "troubleshooting": "Rozwiązywanie problemów", "download": "Pobierz", "language": "Wybierz język", "footer": "Nawigacja w stopce", "status": "Kod źródłowy", "legal": "Informacje prawne", "privacy": "Prywatność", "support": "Wesprzyj", "web_installer": "Instalator webowy", "support_via": "Buy Me a Coffee", "tagline": "Darmowe mapy na zegarek Garmin lub Edge.", "col_install": "Instalacja", "col_help": "Pomoc", "col_project": "Projekt", "guide_watch": "Poradnik: zegarek", "guide_edge": "Poradnik: Edge", "guide_linux": "Poradnik: Linux"},
    "cs": {"flag": "🇨🇿", "name": "Čeština", "home": "Domů Terento", "primary": "Hlavní navigace", "menu": "Menu", "close": "Zavřít menu", "about": "O projektu", "styles": "Mapy", "compatibility": "Kompatibilita", "guide": "Průvodce", "faq": "FAQ", "troubleshooting": "Řešení potíží", "download": "Stáhnout", "language": "Vybrat jazyk", "footer": "Navigace v zápatí", "status": "Zdrojový kód", "legal": "Právní informace", "privacy": "Soukromí", "support": "Přispět", "web_installer": "Webový instalátor", "support_via": "Buy Me a Coffee", "tagline": "Mapy zdarma pro hodinky Garmin i Edge.", "col_install": "Instalace", "col_help": "Nápověda", "col_project": "Projekt", "guide_watch": "Návod pro hodinky", "guide_edge": "Návod pro Edge", "guide_linux": "Návod pro Linux"},
    "it": {"flag": "🇮🇹", "name": "Italiano", "home": "Home Terento", "primary": "Navigazione principale", "menu": "Menu", "close": "Chiudi menu", "about": "Informazioni", "styles": "Mappe", "compatibility": "Compatibilità", "guide": "Guida", "faq": "FAQ", "troubleshooting": "Risoluzione dei problemi", "download": "Scarica", "language": "Scegli la lingua", "footer": "Navigazione del piè di pagina", "status": "Codice sorgente", "legal": "Note legali", "privacy": "Privacy", "support": "Dona", "web_installer": "Installer web", "support_via": "Buy Me a Coffee", "tagline": "Mappe gratuite per il tuo orologio Garmin o Edge.", "col_install": "Installa", "col_help": "Aiuto", "col_project": "Progetto", "guide_watch": "Guida orologio", "guide_edge": "Guida Edge", "guide_linux": "Guida Linux"},
}


def localized_root(locale: str) -> str:
    return "/" if locale == "en" else f"/{locale}/"


def route_for(locale: str, route: str) -> str:
    return f"{localized_root(locale)}{route}"


def umami_attributes(event: str, location: str) -> str:
    return f' data-umami-event="{event}" data-umami-event-location="{location}"'


def language_links(locale: str, route: str, location: str, in_page: bool = False) -> str:
    links = []
    for candidate, candidate_copy in LOCALES.items():
        href = route_for(candidate, route)
        current = ' aria-current="page"' if candidate == locale else ""
        tag = "button" if in_page else "a"
        destination = 'type="button"' if in_page else f'href="{href}"'
        links.append(f'<{tag} class="language-option" {destination} data-language-switch="{candidate}" lang="{candidate}" aria-label="{candidate_copy["name"]}"{current}{umami_attributes("language-switch-click", location)}><span class="language-option-flag" aria-hidden="true">{candidate_copy["flag"]}</span><span>{candidate_copy["name"]}</span></{tag}>')
    return "".join(links)


def shell(locale: str, route: str, page: str) -> tuple[str, str]:
    copy = LOCALES[locale]
    root = localized_root(locale)
    web_installer = WEB_INSTALLER_URL if locale == "en" else f"/{locale}{WEB_INSTALLER_URL}"
    compatibility = route_for(locale, "compatibility/")
    download = route_for(locale, "download/")
    guide = route_for(locale, "guides/install-garmin-maps-mac/")
    troubleshooting = route_for(locale, "guides/troubleshooting/")
    route_for_language = route if page in {"about", "compatibility", "download", "guide", "troubleshooting", "linux-guide", "edge-guide", "map-styles"} else ""
    nav = {"about": route_for(locale, "about/"), "compatibility": compatibility, "styles": route_for(locale, "map-styles/"), "guide": guide, "faq": f"{root}#faq", "troubleshooting": troubleshooting, "download": download}
    active = {"about": page == "about", "compatibility": page == "compatibility", "styles": page == "map-styles", "guide": page == "guide", "troubleshooting": page == "troubleshooting", "download": page == "download"}
    nav_events = {
        "about": "navigation-link-click",
        "styles": "maps-link-click",
        "compatibility": "compatibility-link-click",
        "guide": "guide-link-click",
        "faq": "faq-link-click",
        "troubleshooting": "guide-link-click",
        "download": "download-cta-click",
    }

    def nav_link(key: str, variant: str = "", location: str = "header-nav") -> str:
        current = ' aria-current="page"' if active.get(key) else ""
        class_attribute = f' class="{variant}"' if variant else ""
        return f'<a{class_attribute} href="{nav[key]}" data-shell-copy="{key}" data-shell-route="{key}"{current}{umami_attributes(nav_events[key], location)}>{copy[key]}</a>'
    language_menu = f'''<details class="language-menu">
          <summary class="language-trigger" data-shell-aria="language" aria-label="{copy["language"]}"><span class="language-code" aria-hidden="true">{locale.upper()}</span></summary>
          <div class="language-options">{language_links(locale, route_for_language, "header-language", page in {"legal", "privacy"})}</div>
        </details>'''
    header = f'''<header class="site-header">
      <div class="shell header-inner">
        <a class="brand-lockup" href="{root}" data-shell-aria="home" data-shell-root aria-label="{copy["home"]}"{umami_attributes("home-link-click", "header-brand")}>
          <img src="/assets/logo-sky.svg" alt="" width="40" height="40">
          <span>Terento</span>
        </a>
        <nav class="primary-nav" data-shell-aria="primary" aria-label="{copy["primary"]}">
          {nav_link("compatibility")}{nav_link("styles")}{nav_link("guide")}{nav_link("about")}{nav_link("download", "download-action")}
          <span class="language-switcher">{language_menu}</span>
        </nav>
        <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="mobile-nav" data-menu-label="{copy["menu"]}" data-close-label="{copy["close"]}" aria-label="{copy["menu"]}">
          <span class="menu-toggle-icon" aria-hidden="true"><span></span><span></span><span></span></span>
          <span class="menu-toggle-text" data-shell-copy="menu">{copy["menu"]}</span>
        </button>
      </div>
      <div class="mobile-nav" id="mobile-nav" hidden>
        <div class="shell mobile-nav-inner">
          <nav class="mobile-nav-links" data-shell-aria="primary" aria-label="{copy["primary"]}">
            {nav_link("compatibility", location="mobile-nav")}{nav_link("styles", location="mobile-nav")}{nav_link("guide", location="mobile-nav")}{nav_link("about", location="mobile-nav")}{nav_link("download", location="mobile-nav")}
          </nav>
          <div class="mobile-nav-language"><details class="language-menu mobile-language-menu">
            <summary class="language-trigger" data-shell-aria="language" aria-label="{copy["language"]}"><span class="mobile-language-label">{copy["name"]}</span></summary>
            <div class="language-options">{language_links(locale, route_for_language, "mobile-language", page in {"legal", "privacy"})}</div>
          </details></div>
        </div>
      </div>
    </header>'''
    def footer_link(key: str, href: str, event: str) -> str:
        current = ' aria-current="page"' if active.get(key) else ""
        return f'<a href="{href}" data-shell-copy="{key}"{current}{umami_attributes(event, "footer-nav")}>{copy[key]}</a>'
    active.update({"guide_watch": page == "guide", "guide_edge": page == "edge-guide", "guide_linux": page == "linux-guide"})
    footer = f'''<footer class="site-footer">
      <div class="shell footer-grid">
        <div class="footer-identity">
          <a class="brand-lockup footer-brand" href="{root}" data-shell-aria="home" data-shell-root aria-label="{copy["home"]}"{umami_attributes("home-link-click", "footer-brand")}>
            <img src="/assets/logo-white.svg" alt="" width="32" height="32">
            <span>Terento</span>
          </a>
          <p class="footer-tagline" data-shell-copy="tagline">{copy["tagline"]}</p>
          <div class="footer-actions">
          <a class="footer-support-link" data-support-link href="https://buymeacoffee.com/vooz2" target="_blank" rel="noopener noreferrer"><svg class="footer-support-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg><span data-shell-copy="support">{copy["support"]}</span><span class="footer-support-via">{copy["support_via"]}</span></a>
          <a class="footer-project-link" data-project-link href="https://github.com/VooZ2/terento" target="_blank" rel="noopener noreferrer"><svg class="footer-support-icon" viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" focusable="false"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/></svg><span data-shell-copy="status">{copy["status"]}</span><span class="footer-support-via">GitHub</span></a>
          </div>
        </div>
        <nav class="footer-nav" data-shell-aria="footer" aria-label="{copy["footer"]}">
          <div class="footer-column"><h2 class="footer-heading" data-shell-copy="col_install">{copy["col_install"]}</h2>{nav_link("download", location="footer-nav")}<a data-shell-copy="web_installer" href="{web_installer}"{umami_attributes("web-installer-link-click", "footer-nav")}>{copy["web_installer"]}</a>{nav_link("styles", location="footer-nav")}{nav_link("compatibility", location="footer-nav")}</div>
          <div class="footer-column"><h2 class="footer-heading" data-shell-copy="col_help">{copy["col_help"]}</h2>{footer_link("guide_watch", guide, "guide-link-click")}{footer_link("guide_edge", route_for(locale, "guides/install-garmin-maps-edge-mac/"), "guide-link-click")}{footer_link("guide_linux", route_for(locale, "guides/install-garmin-maps-linux/"), "guide-link-click")}{nav_link("troubleshooting", location="footer-nav")}{nav_link("faq", location="footer-nav")}</div>
          <div class="footer-column"><h2 class="footer-heading" data-shell-copy="col_project">{copy["col_project"]}</h2>{nav_link("about", location="footer-nav")}<a data-shell-copy="legal" href="/legal/"{umami_attributes("legal-link-click", "footer-nav")}>{copy["legal"]}</a><a data-shell-copy="privacy" href="/privacy/"{umami_attributes("privacy-link-click", "footer-nav")}>{copy["privacy"]}</a></div>
        </nav>
      </div>
      <div class="shell footer-bottom"><p>© 2026 Terento Project</p></div>
    </footer>'''
    if page in {"legal", "privacy"}:
        translations = json.dumps(LOCALES, ensure_ascii=False).replace("<", "\\u003c")
        footer += f'<script type="application/json" id="shell-translations">{translations}</script>'
    return header, footer


def normalize_h1_punctuation(source: str) -> str:
    """Keep public H1s consistent: they do not end with a full stop."""
    def replace(match: re.Match[str]) -> str:
        content = re.sub(r"\s*\.\s*$", "", match.group(2))
        return f"{match.group(1)}{content}{match.group(3)}"

    return re.sub(
        r'(<h1\b[^>]*>)([\s\S]*?)(</h1>)',
        replace,
        source,
    )


def _internal_route(path: str, suffix: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized == suffix.rstrip("/") or normalized.endswith("/" + suffix.rstrip("/"))


def _is_local_home(path: str) -> bool:
    return bool(re.fullmatch(r"/(?:[a-z]{2}/)?", path))


def _add_attribute(tag: str, name: str, value: str) -> str:
    if re.search(rf'\s{re.escape(name)}="', tag):
        return tag
    return f'{tag[:-1]} {name}="{value}">' if tag.endswith(">") else tag


def _internal_link_metadata(tag: str, page: str) -> tuple[str, str] | None:
    attributes = dict(re.findall(r'([\w:-]+)="([^"]*)"', tag))
    href = attributes.get("href", "")
    if not (href.startswith("/") or href.startswith("#")):
        return None
    path = href.split("?", 1)[0].split("#", 1)[0] or "/"
    classes = set(attributes.get("class", "").split())
    page_location = {
        "home": "home-content",
        "about": "about-content",
        "compatibility": "compatibility-content",
        "download": "download-content",
        "guide": "guide-content",
        "troubleshooting": "troubleshooting-content",
        "linux-guide": "linux-guide-content",
        "edge-guide": "edge-guide-content",
        "map-styles": "map-styles-content",
        "legal": "legal-content",
        "privacy": "privacy-content",
        "404": "not-found",
        "redirect": "redirect",
    }.get(page, "public-content")

    if "language-option" in classes:
        return "language-switch-click", "language-switcher"
    if "brand-lockup" in classes:
        return "home-link-click", "footer-brand" if "footer-brand" in classes else "header-brand"
    if "skip-link" in classes:
        return "internal-link-click", "skip-link"
    if "hero-compatibility-link" in classes:
        return "compatibility-link-click", "home-hero"
    if "hero-download-action" in classes:
        return "download-cta-click", "home-hero"
    if "compatibility-guide-link" in classes:
        return "guide-link-click", "compatibility-community-testing"
    if "download-info-link" in classes:
        return ("guide-link-click", "download-page") if _internal_route(path, "guides/install-garmin-maps-mac") else ("compatibility-link-click", "download-page")
    if "guide-step-link" in classes:
        return "download-cta-click", "guide-step"
    if href.startswith("#"):
        return "faq-link-click" if href.split("#", 1)[1] == "faq" else "internal-link-click", page_location
    if _is_local_home(path):
        return "home-link-click", page_location
    if _internal_route(path, "compatibility"):
        return "compatibility-link-click", page_location
    if _internal_route(path, "guides/install-garmin-maps-mac") or _internal_route(path, "guides/troubleshooting") or _internal_route(path, "guides/install-garmin-maps-linux") or _internal_route(path, "guides/install-garmin-maps-edge-mac"):
        return "guide-link-click", page_location
    if _internal_route(path, "download"):
        return "download-cta-click", page_location
    if _internal_route(path, "map-styles"):
        return "maps-link-click", page_location
    if _internal_route(path, "about"):
        return "navigation-link-click", page_location
    if _internal_route(path, "legal"):
        return "legal-link-click", page_location
    if _internal_route(path, "privacy"):
        return "privacy-link-click", page_location
    return "internal-link-click", page_location


def normalize_internal_link_events(source: str, page: str) -> str:
    """Give every same-site anchor a stable Umami event and page/location."""
    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        metadata = _internal_link_metadata(tag, page)
        if metadata is None:
            return tag
        event, location = metadata
        tag = _add_attribute(tag, "data-umami-event", event)
        return _add_attribute(tag, "data-umami-event-location", location)

    return re.sub(r"<a\b[^>]*>", replace, source, flags=re.IGNORECASE)


def normalize_email_links(source: str, page: str) -> str:
    """Obfuscate public mailto addresses and attach support analytics metadata."""
    location = "privacy-contact" if page == "privacy" else f"{page}-contact"

    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        attributes = dict(re.findall(r'([\w:-]+)="([^"]*)"', tag))
        href = attributes.get("href", "")
        obfuscated_href = href.replace("@", "&#64;", 1)
        if href != obfuscated_href:
            tag = re.sub(r'href="[^"]*"', f'href="{obfuscated_href}"', tag, count=1)
        tag = _add_attribute(tag, "data-umami-event", "support-link-click")
        tag = _add_attribute(tag, "data-umami-event-location", location)
        return _add_attribute(tag, "data-umami-event-channel", "email")

    source = re.sub(r'<a\b[^>]*href="mailto:[^"]+"[^>]*>', replace, source, flags=re.IGNORECASE)
    # Cloudflare Email Obfuscation would rewrite these to /cdn-cgi/ links that crawlers see as 404.
    return re.sub(
        r'(?<!<!--email_off-->)(<a\b[^>]*href="mailto:[^"]+"[^>]*>.*?</a>)',
        r'<!--email_off-->\1<!--/email_off-->', source, flags=re.IGNORECASE | re.DOTALL,
    )


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
            (f"site/{prefix}guides/troubleshooting/index.html", locale, "troubleshooting"),
            (f"site/{prefix}guides/install-garmin-maps-linux/index.html", locale, "linux-guide"),
            (f"site/{prefix}guides/install-garmin-maps-edge-mac/index.html", locale, "edge-guide"),
            (f"site/{prefix}map-styles/index.html", locale, "map-styles"),
        ])
    result.extend([("site/legal/index.html", "en", "legal"), ("site/privacy/index.html", "en", "privacy")])
    return result


def standalone_files() -> list[tuple[str, str]]:
    return [("site/404.html", "404"), ("site/supported-watches/index.html", "redirect")]


def main() -> None:
    for relative, locale, page in files():
        path = ROOT / relative
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        header, footer = shell(locale, "about/" if page == "about" else "compatibility/" if page == "compatibility" else "download/" if page == "download" else "guides/install-garmin-maps-mac/" if page == "guide" else "guides/troubleshooting/" if page == "troubleshooting" else "guides/install-garmin-maps-linux/" if page == "linux-guide" else "guides/install-garmin-maps-edge-mac/" if page == "edge-guide" else "map-styles/" if page == "map-styles" else "", page)
        source, header_count = re.subn(r'<header class="site-header">[\s\S]*?</header>', header, source, count=1)
        if not header_count:
            raise SystemExit(f"missing header in {relative}")
        source, footer_count = re.subn(r'<footer class="site-footer">[\s\S]*?</footer>(?:<script type="application/json" id="shell-translations">[\s\S]*?</script>)?', footer, source, count=1)
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
            r'(/assets/app/optimized/your-garmin-\d+\.(?:avif|webp|png))(?:\?v=[^"\s]+)?',
            rf'\1?v={IMAGE_VERSION}',
            source,
        )
        source = re.sub(
            r'(/assets/app/optimized/(?:your-garmin|install-maps|installing-maps|manage-maps|map-selected|maps-done|ready-to-install)-\d+\.(?:avif|webp|png))(?:\?v=[^"\s]+)?',
            rf'\1?v={IMAGE_VERSION}', source,
        )
        def screenshot_sources(match):
            picture = match.group(0)
            if not re.search(r'/assets/app/optimized/(?:install-maps|manage-maps)-', picture):
                return picture
            picture = re.sub(
                r'(/assets/app/optimized/(?:install-maps|manage-maps))-1280\.(avif|webp)(\?v=[^"\s,]+) 1280w(?!,)',
                r'\1-1280.\2\3 1280w, \1-1600.\2\3 1600w', picture,
            )
            return re.sub(r'((?:install-maps|manage-maps))-1280\.png', r'\1-1600.png', picture)
        source = re.sub(r'<picture>[\s\S]*?</picture>', screenshot_sources, source)
        def screenshot_dimensions(match):
            return re.sub(r'width="\d+" height="\d+"', 'width="2358" height="1575"', match.group(0))
        source = re.sub(
            r'<img\b[^>]*src="/assets/app/optimized/(?:your-garmin|install-maps|installing-maps|manage-maps|map-selected|maps-done|ready-to-install)-[^>]*>',
            screenshot_dimensions, source,
        )
        source = source.replace('width="2205" height="1348"', 'width="2198" height="1335"')
        source = source.replace('width="2200" height="1346"', 'width="2198" height="1335"')
        source = re.sub(r'\s*<script defer src="/localized-content\.js[^"\s]*"></script>', "", source)
        source = re.sub(
            r'(?:<script defer src="/page-language\.js\?v=[^"\s]+"></script>\s*)?'
            r'<script defer src="/(privacy|legal)-language\.js\?v=[^"\s]+"></script>',
            rf'<script defer src="/page-language.js?v={PAGE_LANGUAGE_VERSION}"></script>\n'
            rf'    <script defer src="/\1-language.js?v={PAGE_LANGUAGE_VERSION}"></script>',
            source,
        )
        source = re.sub(r'(/language\.js\?v=)[^"\s]+', rf'\g<1>{LANGUAGE_VERSION}', source)
        source = re.sub(r'(/privacy-consent\.js\?v=)[^"\s]+', rf'\g<1>{UMAMI_SCRIPT_VERSION}', source)
        source = re.sub(
            r'(<script defer src="/privacy-consent\.js\?v=[^"\s]+"></script>)(?:\s*\1)+',
            r'\1',
            source,
        )
        if page == "download":
            recommended = {"en": "Recommended", "de": "Empfohlen", "fr": "Recommandé", "pl": "Zalecane", "cs": "Doporučeno", "it": "Consigliato"}[locale]
            source = re.sub(r'\s*<span class="download-recommended">[^<]*</span>', "", source)
            source = re.sub(r'(<a class="download-action download-action-primary"[^>]*>)([^<]*)(</a>)', lambda match: match[1] + match[2] + f' <span class="download-recommended">{recommended}</span>' + match[3], source)
        if page == "compatibility":
            source = re.sub(r'(/compatibility/compatibility-data\.js\?v=)[^"\s]+', rf'\g<1>{COMPATIBILITY_VERSION}', source)
            source = re.sub(r'(/compatibility/compatibility-locales\.js\?v=)[^"\s]+', rf'\g<1>{COMPATIBILITY_LOCALES_VERSION}', source)
            source = re.sub(r'(/compatibility/compatibility\.js\?v=)[^"\s]+', rf'\g<1>{COMPATIBILITY_VERSION}', source)
        source = re.sub(r'(\/provider-list\.js\?v=)[^"\s]+', rf'\g<1>{PROVIDER_SCRIPT_VERSION}', source)
        source = normalize_h1_punctuation(source)
        source = normalize_internal_link_events(source, page)
        source = normalize_email_links(source, page)
        path.write_text(source, encoding="utf-8")
    for relative, page in standalone_files():
        path = ROOT / relative
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        source = re.sub(r'(/privacy-consent\.js\?v=)[^"\s]+', rf'\g<1>{UMAMI_SCRIPT_VERSION}', source)
        source = re.sub(r'(\/styles\.css\?v=)[^"\s]+', rf'\g<1>{STYLE_VERSION}', source)
        source = re.sub(r'(\/provider-list\.js\?v=)[^"\s]+', rf'\g<1>{PROVIDER_SCRIPT_VERSION}', source)
        source = normalize_h1_punctuation(source)
        source = normalize_internal_link_events(source, page)
        source = normalize_email_links(source, page)
        path.write_text(source, encoding="utf-8")
    print("Synchronized static public headers and footers.")


if __name__ == "__main__":
    main()
