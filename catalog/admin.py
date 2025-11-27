from django.contrib import admin
from .models import Category, Course, Enrollment, Review, Lesson, LessonProgress, SupportTicket, Bundle, Announcement, Quiz, Question

admin.site.register(Quiz)
admin.site.register(Question)
admin.site.register(Announcement)
admin.site.register(Bundle)
admin.site.register(SupportTicket)
admin.site.register(Lesson)
admin.site.register(Category)
admin.site.register(Course)