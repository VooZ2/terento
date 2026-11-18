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
    "mountain": '<path d="m8 3 4 8 5-5 5 15H2L8 3z"/>',
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


def store_download(href: str, label: str, extra_class: str = "", attributes: str = "") -> str:
    """The primary Download button that sits beside Apple's Mac App Store badge.

    One markup and one class (.download-action--store) for the home hero and the Download
    page, so the two cannot drift apart: 40px tall like the badge, Lucide download icon,
    natural width from padding (translated labels still fit). No license comment in the
    SVG: the Download page HTML may carry only the release version (THIRD_PARTY_NOTICES.md).
    """
    classes = " ".join(filter(None, ("download-action", "download-action--store", extra_class)))
    extra = f" {attributes}" if attributes else ""
    return f'<a class="{classes}" href="{href}"{extra}>{icon("download", "download-action-icon", license_comment=False)}<span>{label}</span></a>'
