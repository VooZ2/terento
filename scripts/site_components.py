"""Shared markup for the site refresh components (.callout, .cta-band, icons, trust strip).

Loaded with runpy by the page generators. Icons are original lucide-static
v0.460.0 path data (ISC, see THIRD_PARTY_NOTICES.md) at the brand 1.75 px stroke.
"""

from __future__ import annotations

LUCIDE = {
    "shield-check": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "triangle-alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
    "layers": '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "bike": '<circle cx="18.5" cy="17.5" r="3.5"/><circle cx="5.5" cy="17.5" r="3.5"/><circle cx="15" cy="5" r="1"/><path d="M12 17.5V14l-3-3 4-3 2 3h2"/>',
    "laptop": '<path d="M20 16V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v9m16 0H4m16 0 1.28 2.55a1 1 0 0 1-.9 1.45H3.62a1 1 0 0 1-.9-1.45L4 16"/>',
    "send": '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
}


def icon(name: str, css_class: str = "", license_comment: bool = True) -> str:
    class_attr = f' class="{css_class}"' if css_class else ""
    comment = "<!-- @license lucide-static v0.460.0 - ISC -->" if license_comment else ""
    return (
        f'<svg{class_attr} aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        f'{comment}{LUCIDE[name]}</svg>'
    )


def callout(body_html: str, kind: str = "info", extra_class: str = "") -> str:
    """A note or warning. kind 'info' or 'warning' picks the icon; the text carries the meaning."""
    name = "triangle-alert" if kind == "warning" else "info"
    classes = " ".join(filter(None, ("callout", f"callout--{kind}", extra_class)))
    return f'<div class="{classes}">{icon(name)}<div>{body_html}</div></div>'


def cta_band(title: str, body_html: str, actions_html: str, extra_class: str = "") -> str:
    """Closing call to action; the title is a <p>, never a heading."""
    classes = " ".join(filter(None, ("cta-band", extra_class)))
    body = f"<p>{body_html}</p>" if body_html else ""
    return (
        f'<div class="{classes}"><div class="cta-band__copy"><p class="cta-band__title">{title}</p>{body}</div>'
        f'<div class="cta-band__actions">{actions_html}</div></div>'
    )


def primary_action(href: str, label: str, extra_class: str = "", attributes: str = "", icon_name: str = "download") -> str:
    """The one primary button on every page (Home hero and Mac app card, Download page,
    install guides). 40px tall with a 44px touch target, 10px radius, 15px/600, a Lucide
    icon (download; globe for the web installer), natural width from padding so translated
    labels fit. No license comment in the SVG: the Download page HTML may carry only the
    release version (THIRD_PARTY_NOTICES.md).
    """
    classes = " ".join(filter(None, ("download-action", "download-action--store", extra_class)))
    extra = f" {attributes}" if attributes else ""
    return f'<a class="{classes}" href="{href}"{extra}>{icon(icon_name, "download-action-icon", license_comment=False)}<span>{label}</span></a>'


def store_download(href: str, label: str, extra_class: str = "", attributes: str = "") -> str:
    """The Download button beside Apple's Mac App Store badge (Home hero, Download page)."""
    return primary_action(href, label, extra_class, attributes)


def secondary_action(href: str, label: str, extra_class: str = "", attributes: str = "", icon_name: str = "") -> str:
    """The secondary button (outline, same 40px size as the primary). At most one per group."""
    classes = " ".join(filter(None, ("button-secondary", extra_class)))
    extra = f" {attributes}" if attributes else ""
    glyph = icon(icon_name, "download-action-icon", license_comment=False) if icon_name else ""
    return f'<a class="{classes}" href="{href}"{extra}>{glyph}<span>{label}</span></a>'


# Shared end-of-page call to action (every page except Download): one line, the primary
# Download for Mac button and a text link to the web installer.
END_CTA = {
    "en": ("Put a free map on your Garmin", "Download for Mac", "Use the web installer", "Open the web installer"),
    "de": ("Bring eine kostenlose Karte auf dein Garmin", "Für Mac herunterladen", "Web-Installer verwenden", "Web-Installer öffnen"),
    "fr": ("Installez une carte gratuite sur votre Garmin", "Télécharger pour Mac", "Utiliser l’installateur web", "Ouvrir l’installateur web"),
    "pl": ("Wgraj darmową mapę na swojego Garmina", "Pobierz na Maca", "Użyj instalatora webowego", "Otwórz instalator webowy"),
    "cs": ("Nahrajte do svého Garminu mapu zdarma", "Stáhnout pro Mac", "Použít webový instalátor", "Otevřít webový instalátor"),
    "it": ("Metti una mappa gratuita sul tuo Garmin", "Scarica per Mac", "Usa l’installer web", "Apri l’installer web"),
}


def end_cta(locale: str, location: str, web_first: bool = False) -> str:
    """The closing band. web_first (Linux guide): the web installer is the primary action and the
    Mac download is left out, because the Mac app can't run there."""
    prefix = "" if locale == "en" else f"/{locale}"
    title, download, web, web_open = END_CTA[locale]
    if web_first:
        actions = primary_action(f"{prefix}/install/", web_open, "", f'data-umami-event="web-installer-link-click" data-umami-event-location="{location}"', "globe")
    else:
        actions = (
            primary_action(f"{prefix}/download/", download, "", f'data-umami-event="download-cta-click" data-umami-event-location="{location}"')
            + f'<a class="text-link" href="{prefix}/install/" data-umami-event="web-installer-link-click" data-umami-event-location="{location}">{web}</a>'
        )
    return cta_band(title, "", actions, "end-cta")
