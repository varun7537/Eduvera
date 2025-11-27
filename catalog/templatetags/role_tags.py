# catalog/templatetags/role_tags.py
from django import template

register = template.Library()

@register.filter
def in_group(user, group_name):
    return user.is_authenticated and user.groups.filter(name=group_name).exists()
