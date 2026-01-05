from django import template
import json

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key."""
    if dictionary is None:
        return None
    return dictionary.get(str(key))

@register.filter
def pprint(value):
    """Pretty print JSON data."""
    try:
        if isinstance(value, str):
            value = json.loads(value)
        return json.dumps(value, indent=2, sort_keys=True)
    except:
        return str(value)
