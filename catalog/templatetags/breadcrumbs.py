from django import template

register = template.Library()

@register.inclusion_tag('catalog/breadcrumbs.html')
def breadcrumbs(course=None, module=None, lesson=None):
    return {
        'course': course,
        'module': module,
        'lesson': lesson
    }
