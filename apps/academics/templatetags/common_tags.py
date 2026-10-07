from django import template

register = template.Library()


@register.filter(name='split')
def split_filter(value, delimiter=','):
    """
    Splits a string by a given delimiter.
    Usage:
        {% for item in "9,10,11,12"|split:"," %}
    """
    if value is None:
        return []
    return [item.strip() for item in str(value).split(str(delimiter))]


@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Dictionary lookup by dynamic key.
    Usage:
        {{ my_dict|get_item:dynamic_key }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
