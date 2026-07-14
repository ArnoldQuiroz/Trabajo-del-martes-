from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    if not mapping:
        return 0
    try:
        return mapping.get(int(key), 0)
    except (TypeError, ValueError):
        return mapping.get(key, 0)
