"""Custom template tags and filters for the downloader app."""

import json as _json

from django import template

register = template.Library()


@register.filter
def json(value):
    """Serialize a Python value to a JSON string for use in templates."""
    return _json.dumps(value)


@register.filter
def status_badge_class(status):
    """Map a job status string to a CSS badge class."""
    mapping = {
        "queued": "badge-queued",
        "running": "badge-running",
        "completed": "badge-completed",
        "failed": "badge-failed",
        "cancelled": "badge-cancelled",
    }
    return mapping.get(status, "badge-queued")


@register.simple_tag
def active_check(request, url_name):
    """Return 'active' if the current URL matches url_name."""
    if hasattr(request, 'resolver_match') and request.resolver_match:
        if request.resolver_match.url_name == url_name:
            return "active"
    return ""
