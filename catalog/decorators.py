# catalog/decorators.py

from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.contrib.auth.views import redirect_to_login

# ------------------------------------------------------------------
# 1. Simple group-based access (e.g. @group_required('Student'))
# ------------------------------------------------------------------
def group_required(group_name):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())

            if request.user.is_superuser or request.user.groups.filter(name=group_name).exists():
                return view_func(request, *args, **kwargs)

            raise PermissionDenied("You don't have permission to access this page.")
        return _wrapped_view
    return decorator


# ------------------------------------------------------------------
# 2. Special decorator: allows Instructor group OR the actual course owner
# ------------------------------------------------------------------
def instructor_or_course_owner(view_func):
    """
    Use on views that receive `course_id` in URL kwargs or args.
    Allows access if user is:
      • superuser
      • in 'Instructor' group
      • OR is the instructor assigned to this specific course
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        if request.user.groups.filter(name='Instructor').exists():
            return view_func(request, *args, **kwargs)

        # Extract course_id from kwargs (most common pattern)
        course_id = kwargs.get('course_id') or kwargs.get('pk') or kwargs.get('id')
        if not course_id:
            raise PermissionDenied

        from .models import Course  # Import here to avoid circular import
        try:
            course = get_object_or_404(Course, id=course_id)
            if course.instructor == request.user:
                return view_func(request, *args, **kwargs)
        except Course.DoesNotExist:
            pass

        raise PermissionDenied("You are not the instructor of this course.")
    return _wrapped_view