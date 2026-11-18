"""Shared markup for the site refresh components (.callout, .cta-band, icons, trust strip).

Loaded with runpy by the page generators. Icons are original lucide-static
v0.460.0 path data (ISC, see THIRD_PARTY_NOTICES.md) at the brand 1.75 px stroke.
"""

from __future__ import annotations

LUCIDE = {
    "shield-check": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "triangle-alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
}


def icon(name: str, css_class: str = "") -> str:
    class_attr = f' class="{css_class}"' if css_class else ""
    return (
        f'<svg{class_attr} aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
        f'<!-- @license lucide-static v0.460.0 - ISC -->{LUCIDE[name]}</svg>'
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
