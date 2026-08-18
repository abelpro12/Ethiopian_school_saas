from django import template

register = template.Library()

@register.filter
def dict_get(d, k):
    if not isinstance(d, dict):
        return None
    return d.get(k)
