from django import template

register = template.Library()


@register.filter(name='multiply')
def multiply(value, arg):
    """
    Multiplies two numbers.
    Usage: {{ value|multiply:arg }}
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0  # or '' if you prefer

@register.filter
def divide(value, arg):
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0

@register.filter
def subtract(value, arg):
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def add(value, arg):
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def mul(value, arg):
    return value * arg
