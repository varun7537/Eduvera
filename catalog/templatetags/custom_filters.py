from django import template
register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def multiply(value, arg):
    return float(value) * float(arg)

@register.filter
def split_skills(skills_string):
    if not skills_string:
        return []
    return [skill.strip() for skill in skills_string.split(',') if skill.strip()]