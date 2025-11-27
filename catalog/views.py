from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.db.models import Sum, Avg, Count, Q
from .forms import ReviewForm, SupportTicketForm, PostForm, ReplyForm, AnnouncementForm
from .models import Course, Enrollment, Announcement, Category, Review, Lesson, LessonProgress, SupportTicket, Post, Reply, QuizResult, Bundle, BundleOrder, Quiz, Question, Profile, Student
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch, cm
from reportlab.lib.colors import HexColor, Color
from io import BytesIO
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from django.conf import settings
from reportlab.graphics.shapes import Drawing, Path
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
import uuid
from reportlab.pdfgen import canvas
from django.core.mail import send_mail
import stripe
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.http import FileResponse, Http404
from django.db.models import Count
from django.db import models
from django.contrib.auth.models import User
from zoomus import ZoomClient
import openai
from .utils import load_video_token
from .utils import make_video_token
from django.core import signing
from .decorators import group_required
from django.core.mail import send_mass_mail
from typing import List, Tuple
from django.core.cache import cache
from datetime import datetime


# Example logic in views.py
def get_category_badges(category):
    badges = []

    # Course count badges
    if category.courses.count() == 0:
        badges.append(("empty", "No Courses"))
    elif category.courses.count() > 20:
        badges.append(("mega", "Mega"))
    elif category.courses.count() > 5:
        badges.append(("active", "Active"))

    # Views badges
    if category.views > 200:
        badges.append(("trending", "Trending"))
    elif category.views > 80:
        badges.append(("hot", "Hot"))
    else:
        badges.append(("popular", "Popular"))

    # Custom badges
    if category.is_featured:
        badges.append(("featured", "Featured"))

    return badges

def course_list(request):
    courses = Course.objects.all()
    return render(request, 'catalog/course_list.html', {'courses': courses})

def course_detail(request, pk):
    course = get_object_or_404(Course, pk=pk)

    quizzes = course.quizzes.all()

    # Fetch reviews and lessons
    reviews = course.reviews.select_related('user').all()
    
    # Removed .order_by('order') → field doesn't exist!
    lessons = course.lessons.all()  # This works perfectly
    total_lessons = lessons.count()

    # Default context values
    enrolled = False
    lessons_done = 0
    lesson_progress = {}
    progress = 0

    form = ReviewForm()

    if request.user.is_authenticated:
        # Check if user is enrolled
        enrolled = Enrollment.objects.filter(user=request.user, course=course).exists()

        # Count completed lessons
        lessons_done = LessonProgress.objects.filter(
            user=request.user,
            lesson__course=course,
            completed=True
        ).count()

        # Build progress dictionary for each lesson
        progress_records = LessonProgress.objects.filter(
            user=request.user,
            lesson__in=lessons
        )
        progress_map = {p.lesson_id: p for p in progress_records}
        lesson_progress = {
            lesson.id: progress_map.get(lesson.id)
            for lesson in lessons
        }

        # Handle review submission
        if request.method == 'POST':
            form = ReviewForm(request.POST)
            if form.is_valid():
                review = form.save(commit=False)
                review.user = request.user
                review.course = course
                review.save()
                return redirect('course_detail', pk=pk)
    else:
        if request.method == 'POST':
            return redirect('login')

    # Calculate progress percentage
    if total_lessons > 0:
        progress = int((lessons_done / total_lessons) * 100)

    context = {
        'course': course,
        'reviews': reviews,
        'lessons': lessons,
        'form': form,
        'enrolled': enrolled,
        'progress': progress,
        'lesson_progress': lesson_progress,
        'lessons_done': lessons_done,
        'total_lessons': total_lessons,
        "quizzes": quizzes,
    }

    return render(request, 'catalog/course_detail.html', context)

def search(request):
    query = request.GET.get('q')
    category_id = request.GET.get('category')
    courses = Course.objects.all()

    if query:
        courses = courses.filter(
        Q(title__icontains=query) |
        Q(description__icontains=query) |
        Q(instructor__username__icontains=query) |
        Q(instructor__first_name__icontains=query) |
        Q(instructor__last_name__icontains=query)
    )

    if category_id:
        courses = courses.filter(category_id=category_id)

    categories = Category.objects.all()

    return render(request, 'catalog/search_results.html', {
        'results': courses,
        'query': query,
        'categories': categories,
        'selected_category': int(category_id) if category_id else None,
    })



@login_required
def enroll_course(request, pk):
    course = get_object_or_404(Course, pk=pk)
    Enrollment.objects.get_or_create(user=request.user, course=course)
    return HttpResponseRedirect(reverse('course_detail', args=[pk]))

@login_required
def my_courses(request):
    # Fetch enrollments with related course (avoids N+1 queries)
    enrollments = Enrollment.objects.filter(user=request.user).select_related('course')

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------
    all_count = enrollments.count()
    completed_count = enrollments.filter(is_completed=True).count()
    in_progress_count = enrollments.filter(is_completed=False, progress__gt=0).count()
    new_count = enrollments.filter(progress=0).count()

    # Certificates = completed courses
    certificates_count = completed_count

    # ------------------------------------------------------------------
    # Average progress (across all enrollments)
    # ------------------------------------------------------------------
    avg_result = enrollments.aggregate(avg_progress=Avg('progress'))['avg_progress']
    avg_progress = round(avg_result, 1) if avg_result is not None else 0.0

    # ------------------------------------------------------------------
    # Total learning time – your Course model has `duration` (not `hours`)
    # Assuming duration is stored in minutes or hours – adjust as needed
    # ------------------------------------------------------------------
    total_duration = enrollments.aggregate(
        total=Sum('course__duration')
    )['total'] or 0

    # Optional: convert minutes → hours if your `duration` field is in minutes
    # total_hours = round(total_duration / 60, 1) if total_duration else 0
    # Or keep it as-is if it's already in hours
    total_hours = total_duration  # change this line based on your data

    # ------------------------------------------------------------------
    # Ensure data consistency: completed → progress = 100
    # (Better to do this in model.save(), but safe fallback here)
    # ------------------------------------------------------------------
    to_update = []
    for enrollment in enrollments:
        if enrollment.is_completed and enrollment.progress != 100:
            enrollment.progress = 100
            to_update.append(enrollment)

    if to_update:
        Enrollment.objects.bulk_update(to_update, ['progress'])

    context = {
        'enrollments': enrollments,
        'all_count': all_count,
        'completed_count': completed_count,
        'in_progress_count': in_progress_count,
        'new_count': new_count,
        'certificates_count': certificates_count,
        'avg_progress': avg_progress,
        'total_hours': total_hours,       
    }

    return render(request, 'catalog/my_courses.html', context)

def categories_list(request):
    categories = Category.objects.all()

    context = {
        "categories": categories,
        "category_count": Category.objects.count(),
        "course_count": Course.objects.count(),
        "student_count": Student.objects.count(),
        "success_rate": 90,   # Example static value
    }

    return render(request, 'catalog/categories_list.html', context)


def category_courses(request, category_id):
    category = get_object_or_404(Category, pk=category_id)
    courses = Course.objects.filter(category=category)

    # Count of courses in this category
    course_count = category.courses.count()

    return render(request, 'catalog/category_courses.html', {
        'category': category,
        'courses': courses,
        'course_count': course_count,
    })

@login_required
def profile(request):
    profile, created = Profile.objects.get_or_create(user=request.user)

    enrollments = Enrollment.objects.filter(user=request.user)
    completed_enrollments = enrollments.filter(is_completed=True)
    reviews = Review.objects.filter(user=request.user)

    profile.complete_count = completed_enrollments.count()
    profile.reviews = reviews.count()

    total_courses = enrollments.count()
    profile.progress_percentage = (
        (profile.complete_count / total_courses) * 100 if total_courses > 0 else 0
    )

    profile.save()

    return render(request, 'catalog/profile.html', {
        'profile': profile,
        'enrollments': enrollments,
        'completed_enrollments': completed_enrollments,
        'reviews': reviews,
    })


@login_required
def mark_completed(request, pk):
    enrollment = get_object_or_404(Enrollment, user=request.user, course__pk=pk)
    enrollment.is_completed = True
    enrollment.save()
    return redirect('course_detail', pk=pk)

from .models import Lesson, LessonProgress

@login_required
def mark_lesson_complete(request, lesson_id):
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    progress, created = LessonProgress.objects.get_or_create(
        user=request.user,
        lesson=lesson,
        defaults={'completed': True}
    )
    if not created:
        progress.completed = True
        progress.save()
    return redirect('course_detail', pk=lesson.course.pk)

@login_required
def instructor_dashboard(request):
    # Only show courses for the logged-in instructor
    my_courses = Course.objects.filter(instructor=request.user)
    course_data = []
    for course in my_courses:
        enrolled_students = Enrollment.objects.filter(course=course)
        course_data.append({
            'course': course,
            'enrollments': enrolled_students,
            'num_enrollments': enrolled_students.count()
        })
    return render(request, 'catalog/instructor_dashboard.html', {
        'course_data': course_data
    })

@login_required
def submit_ticket(request):
    if request.method == 'POST':
        form = SupportTicketForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.user = request.user
            ticket.save()
            return redirect('ticket_thanks')
    else:
        form = SupportTicketForm()
    return render(request, 'catalog/submit_ticket.html', {'form': form})

def ticket_thanks(request):
    return render(request, 'catalog/ticket_thanks.html')

@login_required
def course_forum(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    posts = Post.objects.filter(course=course).order_by('-created_at')

    if request.method == 'POST':
        form = PostForm(request.POST)
        if form.is_valid():
            new_post = form.save(commit=False)
            new_post.user = request.user
            new_post.course = course
            new_post.save()

            # Notify instructor
            send_mail(
                subject=f"New Forum Post in {course.title}",
                message=f"{request.user.get_full_name() or request.user.username} "
                        f"posted in the discussion forum of your course '{course.title}'.",
                from_email=None,  # uses DEFAULT_FROM_EMAIL
                recipient_list=[course.instructor.email],
                fail_silently=False,
            )

            return redirect('course_forum', course_id=course_id)
        # If form is invalid → fall through to render with errors
    else:
        form = PostForm()  # GET request → empty form

    # This block runs for GET requests AND for invalid POSTs
    return render(request, 'catalog/course_forum.html', {
        'course': course,
        'posts': posts,
        'form': form,
    })

@login_required
def reply_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if request.method == 'POST':
        form = ReplyForm(request.POST)
        if form.is_valid():
            new_reply = form.save(commit=False)
            new_reply.user = request.user
            new_reply.post = post
            new_reply.save()
            return redirect('course_forum', course_id=post.course.pk)
    return redirect('course_forum', course_id=post.course.pk)


@property
def total_questions(self):
    return self.quiz.questions.count()


@login_required
def download_certificate(request, course_id):
    """Generate and download a professional certificate PDF."""
    
    # Fetch enrollment with validation
    enrollment = get_object_or_404(
        Enrollment, user=request.user, course_id=course_id, is_completed=True
    )
    course = enrollment.course
    
    # Generate unique certificate ID
    certificate_id = f"CERT-{uuid.uuid4().hex[:10].upper()}-{datetime.now().strftime('%Y%m')}"
    
    # Calculate grade and performance
    grade_data = _calculate_grade(request.user, course)
    enrollment.grade = grade_data['display']
    enrollment.save()
    
    # Extract skills
    skills = _extract_skills(course)
    
    # Generate PDF
    buffer = _generate_certificate_pdf(
        user=request.user,
        course=course,
        enrollment=enrollment,
        certificate_id=certificate_id,
        grade_data=grade_data,
        skills=skills
    )
    
    # Prepare response
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in course.title)[:30]
    filename = f"Certificate_{safe_title}_{request.user.username}.pdf"
    
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _calculate_grade(user, course):
    """Calculate grade and performance metrics."""
    quizzes = course.quizzes.all()
    quiz_results = QuizResult.objects.filter(user=user, quiz__in=quizzes)
    
    if not quiz_results.exists():
        return {
            'display': 'Completed',
            'percentage': None,
            'badge': 'CERTIFIED',
            'color': HexColor("#4A90E2")
        }
    
    total_correct = 0
    total_questions = 0
    
    for result in quiz_results:
        question_count = result.quiz.questions.count()
        if question_count > 0:
            total_correct += result.score
            total_questions += question_count
    
    if total_questions == 0:
        return {
            'display': 'Completed',
            'percentage': None,
            'badge': 'CERTIFIED',
            'color': HexColor("#4A90E2")
        }
    
    percentage = (total_correct / total_questions) * 100
    
    # Determine badge and color
    if percentage >= 90:
        badge, color = "DISTINCTION", HexColor("#FFD700")
    elif percentage >= 75:
        badge, color = "MERIT", HexColor("#C0C0C0")
    else:
        badge, color = "PASS", HexColor("#CD7F32")
    
    return {
        'display': f"{percentage:.1f}%",
        'percentage': percentage,
        'badge': badge,
        'color': color
    }


def _extract_skills(course):
    """Extract skills from course, with fallback defaults."""
    default_skills = ["Professional Development", "Problem Solving", "Critical Thinking", "Technical Skills"]
    
    if not hasattr(course, "skills"):
        return default_skills
    
    skills_attr = course.skills
    
    # Handle list
    if isinstance(skills_attr, list):
        return skills_attr if skills_attr else default_skills
    
    # Handle string (comma-separated)
    if isinstance(skills_attr, str):
        parsed = [s.strip() for s in skills_attr.split(",") if s.strip()]
        return parsed if parsed else default_skills
    
    # Handle queryset or relation
    try:
        parsed = [s.name for s in skills_attr.all()]
        return parsed if parsed else default_skills
    except Exception:
        return default_skills


def _generate_certificate_pdf(user, course, enrollment, certificate_id, grade_data, skills):
    """Generate the certificate PDF with enhanced professional design."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(letter))
    width, height = landscape(letter)
    
    # Design constants
    COLORS = {
        'primary': HexColor("#1e40af"),      # Deep blue
        'secondary': HexColor("#475569"),    # Slate gray
        'accent': HexColor("#f59e0b"),       # Gold accent
        'dark': HexColor("#0f172a"),         # Very dark slate
        'light': HexColor("#f8fafc"),        # Light background
        'border': HexColor("#cbd5e1"),       # Border gray
        'gold': HexColor("#d4af37"),         # Gold
    }
    
    PADDING = 45
    
    # Background with decorative elements
    _draw_enhanced_background(pdf, width, height, COLORS)
    
    # Decorative border
    _draw_enhanced_border(pdf, width, height, PADDING, COLORS)
    
    # Logo at top
    _draw_logo_top(pdf, width, height, COLORS)
    
    # Header with organization
    _draw_enhanced_header(pdf, width, height, COLORS)
    
    # Certificate title
    _draw_enhanced_title(pdf, width, height, COLORS)
    
    # Achievement badge
    _draw_achievement_badge(pdf, width, height, grade_data, COLORS)
    
    # Recipient section
    _draw_enhanced_recipient(pdf, width, height, user, COLORS)
    
    # Course title section
    _draw_enhanced_course_title(pdf, width, height, course.title, COLORS)
    
    # Details section with better spacing
    _draw_enhanced_details(pdf, width, height, course, grade_data, enrollment, COLORS)
    
    # Signature section with actual signature
    _draw_enhanced_signature(pdf, width, height, course.instructor, COLORS)
    
    # QR Code for verification
    _draw_enhanced_qr(pdf, enrollment.id, COLORS)
    
    # Footer with certificate ID
    _draw_enhanced_footer(pdf, width, certificate_id, COLORS)
    
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    
    return buffer


def _draw_enhanced_background(pdf, width, height, colors):
    """Draw elegant background with decorative elements."""
    # Base background
    pdf.setFillColor(colors['light'])
    pdf.rect(0, 0, width, height, stroke=0, fill=1)
    
    # Decorative corner patterns (top-left)
    pdf.setFillColor(colors['primary'])
    pdf.setFillAlpha(0.04)
    for i in range(5):
        radius = 60 + (i * 30)
        pdf.circle(-20, height + 20, radius, fill=1, stroke=0)
    
    # Decorative corner patterns (bottom-right)
    for i in range(5):
        radius = 60 + (i * 30)
        pdf.circle(width + 20, -20, radius, fill=1, stroke=0)
    
    pdf.setFillAlpha(1)
    
    # Subtle accent lines
    pdf.setStrokeColor(colors['gold'])
    pdf.setLineWidth(0.5)
    pdf.setStrokeAlpha(0.3)
    
    # Top decorative lines
    for i in range(3):
        y_pos = height - 25 - (i * 3)
        pdf.line(width * 0.3, y_pos, width * 0.7, y_pos)
    
    pdf.setStrokeAlpha(1)


def _draw_enhanced_border(pdf, width, height, padding, colors):
    """Draw elegant multi-layer border."""
    # Outer gold border
    pdf.setStrokeColor(colors['gold'])
    pdf.setLineWidth(3)
    pdf.rect(padding - 10, padding - 10, 
             width - 2 * (padding - 10), 
             height - 2 * (padding - 10), 
             stroke=1, fill=0)
    
    # Middle border
    pdf.setStrokeColor(colors['border'])
    pdf.setLineWidth(1)
    pdf.rect(padding - 5, padding - 5, 
             width - 2 * (padding - 5), 
             height - 2 * (padding - 5), 
             stroke=1, fill=0)
    
    # Inner primary border
    pdf.setStrokeColor(colors['primary'])
    pdf.setLineWidth(2)
    pdf.rect(padding, padding, 
             width - 2 * padding, 
             height - 2 * padding, 
             stroke=1, fill=0)
    
    # Corner decorations
    corner_size = 15
    corners = [
        (padding, padding),  # bottom-left
        (width - padding, padding),  # bottom-right
        (padding, height - padding),  # top-left
        (width - padding, height - padding)  # top-right
    ]
    
    pdf.setFillColor(colors['gold'])
    for x, y in corners:
        pdf.circle(x, y, 4, fill=1, stroke=0)


def _draw_logo_top(pdf, width, height, colors):
    """Draw logo at the top center."""
    logo_path = os.path.join(settings.BASE_DIR, "catalog", "static", "catalog", "images", "logo.png")
    logo_y = height - 65
    
    if os.path.exists(logo_path):
        try:
            pdf.drawImage(
                ImageReader(logo_path), 
                width / 2 - 30, logo_y, 
                width=60, height=60, 
                mask="auto"
            )
        except Exception:
            # Fallback: draw a decorative emblem
            pdf.setFillColor(colors['primary'])
            pdf.setFillAlpha(0.1)
            pdf.circle(width / 2, logo_y + 30, 35, fill=1, stroke=0)
            pdf.setFillAlpha(1)
            
            pdf.setStrokeColor(colors['gold'])
            pdf.setLineWidth(2)
            pdf.circle(width / 2, logo_y + 30, 30, fill=0, stroke=1)
            
            pdf.setFont("Helvetica-Bold", 24)
            pdf.setFillColor(colors['primary'])
            pdf.drawCentredString(width / 2, logo_y + 22, "✓")


def _draw_enhanced_header(pdf, width, height, colors):
    """Draw header with organization name."""
    y = height - 95
    
    pdf.setFont("Helvetica-Bold", 16)
    pdf.setFillColor(colors['primary'])
    pdf.drawCentredString(width / 2, y, "PROFESSIONAL LEARNING INSTITUTE")
    
    # Decorative line under header
    pdf.setStrokeColor(colors['gold'])
    pdf.setLineWidth(1)
    pdf.line(width / 2 - 120, y - 8, width / 2 + 120, y - 8)


def _draw_enhanced_title(pdf, width, height, colors):
    """Draw certificate title with elegant styling."""
    y = height - 145
    
    # Main title
    pdf.setFont("Helvetica-Bold", 52)
    pdf.setFillColor(colors['dark'])
    pdf.drawCentredString(width / 2, y, "CERTIFICATE")
    
    # Subtitle
    pdf.setFont("Helvetica", 20)
    pdf.setFillColor(colors['primary'])
    pdf.drawCentredString(width / 2, y - 30, "OF COMPLETION")
    
    # Decorative underline with ornaments
    line_y = y - 42
    pdf.setStrokeColor(colors['gold'])
    pdf.setLineWidth(2)
    pdf.line(width / 2 - 180, line_y, width / 2 + 180, line_y)
    
    # Ornamental dots
    pdf.setFillColor(colors['gold'])
    pdf.circle(width / 2 - 180, line_y, 4, fill=1, stroke=0)
    pdf.circle(width / 2 + 180, line_y, 4, fill=1, stroke=0)
    pdf.circle(width / 2, line_y, 4, fill=1, stroke=0)


def _draw_achievement_badge(pdf, width, height, grade_data, colors):
    """Draw achievement badge on the right side."""
    badge_x = width - 120
    badge_y = height - 160
    
    # Badge background
    pdf.setFillColor(grade_data['color'])
    pdf.setFillAlpha(0.15)
    pdf.circle(badge_x, badge_y, 35, fill=1, stroke=0)
    pdf.setFillAlpha(1)
    
    # Badge border
    pdf.setStrokeColor(grade_data['color'])
    pdf.setLineWidth(3)
    pdf.circle(badge_x, badge_y, 35, fill=0, stroke=1)
    
    pdf.setLineWidth(1.5)
    pdf.circle(badge_x, badge_y, 28, fill=0, stroke=1)
    
    # Badge text
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(grade_data['color'])
    pdf.drawCentredString(badge_x, badge_y - 4, grade_data['badge'])


def _draw_enhanced_recipient(pdf, width, height, user, colors):
    """Draw recipient section with elegant styling."""
    y = height - 205
    
    # Introductory text
    pdf.setFont("Helvetica", 14)
    pdf.setFillColor(colors['secondary'])
    pdf.drawCentredString(width / 2, y, "This is to certify that")
    
    # Recipient name with elegant styling
    name = (user.get_full_name() or user.username).strip() or "Valued Learner"
    pdf.setFont("Helvetica-Bold", 38)
    pdf.setFillColor(colors['dark'])
    pdf.drawCentredString(width / 2, y - 35, name)
    
    # Elegant underline
    underline_y = y - 48
    pdf.setStrokeColor(colors['gold'])
    pdf.setLineWidth(1.5)
    pdf.line(width / 2 - 220, underline_y, width / 2 + 220, underline_y)
    
    # Decorative dots
    pdf.setFillColor(colors['accent'])
    pdf.circle(width / 2 - 220, underline_y, 3, fill=1, stroke=0)
    pdf.circle(width / 2 + 220, underline_y, 3, fill=1, stroke=0)


def _draw_enhanced_course_title(pdf, width, height, title, colors):
    """Draw course title in an elegant box."""
    y = height - 280
    
    # Introductory text
    pdf.setFont("Helvetica", 14)
    pdf.setFillColor(colors['secondary'])
    pdf.drawCentredString(width / 2, y, "has successfully completed the course")
    
    # Course title box
    box_y = y - 48
    pdf.setFillColor(HexColor("#ffffff"))
    pdf.setStrokeColor(colors['border'])
    pdf.setLineWidth(1.5)
    pdf.roundRect(width / 2 - 280, box_y, 560, 40, 5, fill=1, stroke=1)
    
    # Inner border
    pdf.setStrokeColor(colors['primary'])
    pdf.setStrokeAlpha(0.3)
    pdf.setLineWidth(1)
    pdf.roundRect(width / 2 - 276, box_y + 4, 552, 32, 4, fill=0, stroke=1)
    pdf.setStrokeAlpha(1)
    
    # Course title
    pdf.setFont("Helvetica-Bold", 22)
    pdf.setFillColor(colors['dark'])
    pdf.drawCentredString(width / 2, box_y + 12, title)


def _draw_enhanced_details(pdf, width, height, course, grade_data, enrollment, colors):
    """Draw course details with proper spacing."""
    y = height - 360
    
    # Section title
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(colors['secondary'])
    pdf.drawCentredString(width / 2, y, "COURSE DETAILS")
    
    # Details background card
    card_y = y - 65
    pdf.setFillColor(HexColor("#ffffff"))
    pdf.setStrokeColor(colors['border'])
    pdf.setLineWidth(1)
    pdf.roundRect(width / 2 - 320, card_y, 640, 60, 8, fill=1, stroke=1)
    
    # Get values
    duration = getattr(course, "duration", "Self-Paced")
    hours = getattr(course, "total_hours", "N/A")
    if hours != "N/A":
        hours = f"{hours} Hours"
    
    date = enrollment.completed_at or enrollment.enrolled_at
    date_str = date.strftime("%B %d, %Y") if date else "Date Not Recorded"
    
    # Four columns with proper spacing
    positions = [width / 2 - 210, width / 2 - 70, width / 2 + 70, width / 2 + 210]
    labels = ["DURATION", "HOURS", "SCORE", "COMPLETED"]
    values = [str(duration), str(hours), grade_data['display'], date_str]
    icon_colors = [colors['primary'], HexColor("#10B981"), colors['accent'], HexColor("#8b5cf6")]
    
    for pos, label, value, icon_color in zip(positions, labels, values, icon_colors):
        # Icon circle
        icon_y = card_y + 40
        pdf.setFillColor(icon_color)
        pdf.setFillAlpha(0.15)
        pdf.circle(pos, icon_y, 12, fill=1, stroke=0)
        pdf.setFillAlpha(1)
        
        pdf.setStrokeColor(icon_color)
        pdf.setLineWidth(1.5)
        pdf.circle(pos, icon_y, 12, fill=0, stroke=1)
        
        # Label
        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColor(colors['secondary'])
        pdf.drawCentredString(pos, card_y + 20, label)
        
        # Value with truncation for long dates
        pdf.setFont("Helvetica-Bold", 11)
        pdf.setFillColor(colors['dark'])
        display_value = value if len(value) <= 15 else value[:12] + "..."
        pdf.drawCentredString(pos, card_y + 6, display_value)


def _draw_enhanced_signature(pdf, width, height, instructor, colors):
    """Draw signature section with visual signature."""
    y = 115
    sig_x = width / 2
    
    # Draw a realistic signature (handwritten style)
    pdf.setStrokeColor(colors['primary'])
    pdf.setLineWidth(1.5)
    
    # Signature curve (simulated handwriting)
    path = pdf.beginPath()
    path.moveTo(sig_x - 60, y + 25)
    path.curveTo(sig_x - 40, y + 35, sig_x - 20, y + 20, sig_x, y + 25)
    path.curveTo(sig_x + 20, y + 30, sig_x + 40, y + 15, sig_x + 60, y + 25)
    pdf.drawPath(path, stroke=1, fill=0)
    
    # Signature underline
    path2 = pdf.beginPath()
    path2.moveTo(sig_x - 50, y + 20)
    path2.lineTo(sig_x + 50, y + 22)
    pdf.drawPath(path2, stroke=1, fill=0)
    
    # Signature line
    pdf.setStrokeColor(colors['dark'])
    pdf.setLineWidth(1)
    pdf.line(sig_x - 100, y, sig_x + 100, y)
    
    # Instructor name
    name = instructor.get_full_name() or instructor.username or "Course Instructor"
    pdf.setFont("Helvetica-Bold", 13)
    pdf.setFillColor(colors['dark'])
    pdf.drawCentredString(sig_x, y - 18, name)
    
    # Title
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors['secondary'])
    pdf.drawCentredString(sig_x, y - 32, "Lead Instructor & Authorized Signatory")
    
    # Date seal
    pdf.setStrokeColor(colors['gold'])
    pdf.setFillColor(colors['gold'])
    pdf.setFillAlpha(0.1)
    pdf.circle(sig_x + 150, y + 10, 25, fill=1, stroke=0)
    pdf.setFillAlpha(1)
    pdf.setLineWidth(2)
    pdf.circle(sig_x + 150, y + 10, 25, fill=0, stroke=1)
    
    pdf.setFont("Helvetica-Bold", 8)
    pdf.setFillColor(colors['gold'])
    pdf.drawCentredString(sig_x + 150, y + 12, "VERIFIED")
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(sig_x + 150, y + 3, datetime.now().strftime("%Y"))


def _draw_enhanced_qr(pdf, enrollment_id, colors):
    """Draw QR code with better styling."""
    qr_x = 75
    qr_y = 75
    
    # QR background card
    pdf.setFillColor(HexColor("#ffffff"))
    pdf.setStrokeColor(colors['border'])
    pdf.setLineWidth(1.5)
    pdf.roundRect(qr_x - 15, qr_y - 15, 90, 110, 8, fill=1, stroke=1)
    
    # Title
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(colors['primary'])
    pdf.drawCentredString(qr_x + 30, qr_y + 85, "VERIFY")
    
    # Generate QR code
    verify_url = f"https://yourdomain.com/verify/{enrollment_id}"
    qr_code = qr.QrCodeWidget(verify_url)
    bounds = qr_code.getBounds()
    qw, qh = bounds[2] - bounds[0], bounds[3] - bounds[1]
    d = Drawing(65, 65, transform=[65/qw, 0, 0, 65/qh, 0, 0])
    d.add(qr_code)
    renderPDF.draw(d, pdf, qr_x - 2, qr_y)
    
    # Instruction text
    pdf.setFont("Helvetica", 7)
    pdf.setFillColor(colors['secondary'])
    pdf.drawCentredString(qr_x + 30, qr_y - 8, "Scan to verify")


def _draw_enhanced_footer(pdf, width, certificate_id, colors):
    """Draw footer with certificate ID and details."""
    footer_height = 25
    
    # Footer background
    pdf.setFillColor(colors['primary'])
    pdf.setFillAlpha(0.05)
    pdf.rect(0, 0, width, footer_height, fill=1, stroke=0)
    pdf.setFillAlpha(1)
    
    # Top border line
    pdf.setStrokeColor(colors['gold'])
    pdf.setLineWidth(1)
    pdf.line(0, footer_height, width, footer_height)
    
    # Certificate ID
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(colors['primary'])
    pdf.drawString(160, 12, f"Certificate ID: {certificate_id}")
    
    # Website
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(colors['secondary'])
    pdf.drawCentredString(width / 2, 12, "www.yourdomain.com • contact@yourdomain.com")
    
    # Verification link
    pdf.setFont("Helvetica-Bold", 8)
    pdf.setFillColor(colors['primary'])
    pdf.drawRightString(width - 160, 12, "Verify: yourdomain.com/verify")


@login_required
def take_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    questions = quiz.questions.all()

    # Convert options into a list for each question
    for question in questions:
        question.options = [
            question.option1,
            question.option2,
            question.option3,
            question.option4,
        ]

    if request.method == 'POST':
        score = 0
        total = questions.count()

        for question in questions:
            selected = int(request.POST.get(f"question_{question.id}"))
            if selected == question.correct_option:
                score += 1

        QuizResult.objects.create(user=request.user, quiz=quiz, score=score)

        return render(request, 'catalog/quiz_result.html', {
            'quiz': quiz,
            'score': score,
            'total': total,
        })

    return render(request, 'catalog/take_quiz.html', {
        'quiz': quiz,
        'questions': questions,
    })

@login_required
def take_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    questions = quiz.questions.filter(question_type='MCQ')

    if request.method == 'POST':
        score = 0
        total = questions.count()

        for question in questions:
            selected = request.POST.get(f"question_{question.id}")
            if selected and int(selected) == question.correct_option:
                score += question.marks

        incorrect = total - score

        # Save result
        QuizResult.objects.create(
            user=request.user,
            quiz=quiz,
            score=score,
            total_marks=sum(q.marks for q in questions)
        )

        return render(request, 'catalog/quiz_result.html', {
            'quiz': quiz,
            'score': score,
            'total': total,
            'incorrect': incorrect,
            'total_marks': sum(q.marks for q in questions)
        })

    return render(request, 'catalog/take_quiz.html', {
        'quiz': quiz,
        'questions': questions,
    })

def bundle_list(request):
    bundles = Bundle.objects.all()
    return render(request, 'catalog/bundle_list.html', {'bundles': bundles})

@login_required
def enroll_course(request, pk):
    course = get_object_or_404(Course, pk=pk)
    enrollment, created = Enrollment.objects.get_or_create(user=request.user, course=course)

    if created:
        send_mail(
            subject=f"New Enrollment for {course.title}",
            message=f"{request.user.username} has enrolled in your course: {course.title}.",
            from_email=None,
            recipient_list=[course.instructor.email],
        )

    return redirect('course_detail', pk=pk)


stripe.api_key = settings.STRIPE_SECRET_KEY

@login_required
def buy_bundle(request, bundle_id):
    bundle = get_object_or_404(Bundle, id=bundle_id)
    order = BundleOrder.objects.create(user=request.user, bundle=bundle)

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': bundle.name,
                },
                'unit_amount': int(bundle.price * 100),
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=request.build_absolute_uri(f'/bundles/success/{order.id}/'),
        cancel_url=request.build_absolute_uri('/bundles/'),
    )

    return redirect(checkout_session.url)

@login_required
def bundle_success(request, order_id):
    order = get_object_or_404(BundleOrder, id=order_id, user=request.user)
    order.paid = True
    order.save()

    # Mark user as enrolled in all courses in bundle
    for course in order.bundle.courses.all():
        Enrollment.objects.get_or_create(user=request.user, course=course)

    return render(request, 'catalog/bundle_success.html', {'bundle': order.bundle})

@login_required
def stream_video(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    enrolled = Enrollment.objects.filter(user=request.user, course=lesson.course, is_completed=False).exists()

    if not enrolled:
        raise Http404("Not authorized")

    video_path = lesson.video.path
    return FileResponse(open(video_path, 'rb'), content_type='video/mp4')

@login_required
def lesson_notes(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    note, created = LessonNote.objects.get_or_create(user=request.user, lesson=lesson)

    if request.method == 'POST':
        form = LessonNoteForm(request.POST, instance=note)
        if form.is_valid():
            form.save()
            return redirect('lesson_detail', lesson_id=lesson_id)
    else:
        form = LessonNoteForm(instance=note)

    return render(request, 'courses/lesson_notes.html', {'lesson': lesson, 'form': form})

def create_zoom_meeting(topic, start_time):
    client = ZoomClient(settings.ZOOM_API_KEY, settings.ZOOM_API_SECRET)
    response = client.meeting.create(
        user_id="me",
        topic=topic,
        type=2,  # Scheduled
        start_time=start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        duration=60
    )
    return response['join_url']

@login_required
def schedule_live_class(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if request.method == 'POST':
        topic = request.POST['topic']
        start_time = request.POST['start_time']  # from datetime-local input
        start_dt = datetime.strptime(start_time, "%Y-%m-%dT%H:%M")
        zoom_link = create_zoom_meeting(topic, start_dt)
        LiveClass.objects.create(course=course, topic=topic, start_time=start_dt, zoom_link=zoom_link)
        return redirect('course_detail', pk=course.id)
    return render(request, 'catalog/schedule_live_class.html', {'course': course})


def generate_quiz_from_lesson(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    openai.api_key = settings.OPENAI_API_KEY

    prompt = f"Generate 5 multiple-choice quiz questions with 4 options each based on the following lesson:\n\n{lesson.content}"

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    quiz_data = response.choices[0].message['content']

    # Parse and create quiz in DB
    quiz = Quiz.objects.create(course=lesson.course, title=f"AI Quiz - {lesson.title}")
    # Simple parser (pseudo example)
    for q in quiz_data.split("\n\n"):
        if q.strip():
            Question.objects.create(
                quiz=quiz,
                text=q.split("\n")[0],
                option1="Option A",
                option2="Option B",
                option3="Option C",
                option4="Option D",
                correct_option=1
            )
        return redirect(reverse('quiz_detail', args=[quiz.id]))


def quiz_detail(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    return render(request, 'catalog/quiz_detail.html', {
        'quiz': quiz,
    })


@login_required
def complete_lesson(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    # Mark completion...
    profile = request.user.profile
    profile.points += 10  # Lesson completion
    profile.update_badge()
    return redirect('lesson_detail', lesson_id=lesson.id)

def ajax_search(request):
    query = request.GET.get('q', '')
    results = []
    if query:
        courses = Course.objects.filter(title__icontains=query)[:5]
        results = [{'id': c.id, 'title': c.title} for c in courses]
    return JsonResponse({'results': results})


@login_required
def toggle_bookmark(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    bookmark, created = LessonBookmark.objects.get_or_create(user=request.user, lesson=lesson)
    if not created:
        bookmark.delete()
    return redirect('lesson_detail', lesson_id=lesson_id)

@login_required
def stream_video_with_token(request, token):
    data = load_video_token(token)
    if not data:
        raise Http404("Invalid or expired token")

    lesson_id = data.get('l')
    user_id = data.get('u')

    # ensure token belongs to this user
    if request.user.id != int(user_id):
        raise Http404("Token not for this user")

    lesson = get_object_or_404(Lesson, id=lesson_id)

    # ensure user enrolled in course
    enrolled = Enrollment.objects.filter(user=request.user, course=lesson.course).exists()
    if not enrolled:
        raise Http404("Not authorized")

    # stream file (works in DEBUG; production use signed S3 URLs or protected X-Accel-Redirect)
    if not lesson.video:
        raise Http404("No video")
    return FileResponse(open(lesson.video.path, 'rb'), content_type='video/mp4')

@login_required
def get_video_token_redirect(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if not Enrollment.objects.filter(user=request.user, course=lesson.course).exists():
        raise Http404("Not enrolled")
    token = make_video_token(request.user.id, lesson.id)
    # streaming route will consume token param
    return redirect('stream_video_with_token', token=token)

def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            send_activation_email(request, user)
            return render(request, 'accounts/check_email.html')
    else:
        form = UserCreationForm()
    return render(request, 'accounts/signup.html', {'form': form})

def make_activation_token(user_id):
    return signing.dumps({'user_id': user_id})

def load_activation_token(token, max_age=60*60*24):  # 24 hours
    try:
        data = signing.loads(token, max_age=max_age)
        return data.get('user_id')
    except Exception:
        return None

def send_activation_email(request, user):
    token = make_activation_token(user.id)
    activation_url = request.build_absolute_uri(reverse('activate_account', args=[token]))
    subject = "Activate your account"
    message = f"Hi {user.username},\nPlease activate your account: {activation_url}"
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])

def activate_account(request, token):
    user_id = load_activation_token(token)
    if not user_id:
        return render(request, 'accounts/activation_invalid.html')
    user = get_object_or_404(User, id=user_id)
    user.is_active = True
    user.save()
    login(request, user)
    return render(request, 'accounts/activation_complete.html')


def _ensure_course_owner(request, course):
    if course.instructor != request.user and not request.user.is_superuser:
        raise PermissionDenied

@login_required
def course_announcements(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    # Only enrolled students or the instructor can see announcements
    is_instructor = request.user.is_authenticated and (
        request.user.is_superuser or request.user == course.instructor
    )
    is_enrolled = Enrollment.objects.filter(user=request.user, course=course).exists()
    if not (is_instructor or is_enrolled):
        raise PermissionDenied

    anns = course.announcements.all()
    return render(request, 'catalog/announcements/list.html', {'course': course, 'announcements': anns})

@group_required('Instructor')
def create_announcement(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    _ensure_course_owner(request, course)

    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            ann = form.save(commit=False)
            ann.course = course
            ann.created_by = request.user
            ann.save()
            # OPTIONAL: notify students
            _notify_students_of_announcement(ann)
            return redirect('course_announcements', course_id=course.id)
    else:
        form = AnnouncementForm()

    return render(request, 'catalog/announcements/form.html', {'form': form, 'course': course, 'mode': 'create'})

@group_required('Instructor')
def edit_announcement(request, course_id, ann_id):
    course = get_object_or_404(Course, id=course_id)
    _ensure_course_owner(request, course)

    ann = get_object_or_404(Announcement, id=ann_id, course=course)
    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=ann)
        if form.is_valid():
            form.save()
            return redirect('course_announcements', course_id=course.id)
    else:
        form = AnnouncementForm(instance=ann)
    return render(request, 'catalog/announcements/form.html', {'form': form, 'course': course, 'mode': 'edit'})

@group_required('Instructor')
def delete_announcement(request, course_id, ann_id):
    course = get_object_or_404(Course, id=course_id)
    _ensure_course_owner(request, course)

    ann = get_object_or_404(Announcement, id=ann_id, course=course)
    if request.method == 'POST':
        ann.delete()
        return redirect('course_announcements', course_id=course.id)
    return render(request, 'catalog/announcements/confirm_delete.html', {'announcement': ann, 'course': course})

def notify_students_of_announcement(announcement: Announcement) -> None:
    """
    Notify all enrolled students about a new announcement via email.
    
    This function prepares personalized emails and sends them one by one.
    For high-volume courses, consider using Celery + send_mass_mail in chunks.
    """
    if not announcement.course:
        return

    # Efficiently fetch enrollments with related user data
    enrollments = (
        Enrollment.objects
        .filter(course=announcement.course)
        .select_related('user')
        .only('user__email', 'user__username', 'user__first_name', 'user__last_name')
    )

    messages_to_send: List[Tuple[str, str, str, List[str]]] = []

    course_title = announcement.course.title
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')

    # FIXED: proper fallback chain for instructor name
    instructor_name = (
        announcement.created_by.get_full_name().strip()
        or announcement.created_by.username
        or "Course Instructor"
    )

    for enrollment in enrollments:
        user = enrollment.user
        if not user.email:
            continue  # Skip users without email

        subject = f"[{course_title}] New Announcement: {announcement.title}"

        body = (
            f"Hi {user.get_full_name() or user.username},\n\n"
            f"{announcement.message}\n\n"
            f"— {instructor_name}\n"
            f"Course: {course_title}\n"
        )

        messages_to_send.append((subject, body, from_email, [user.email]))

    if not messages_to_send:
        return

    # Option 1: Simple loop (fine for small/medium courses < 500 students)
    for subject, message, from_email, recipient_list in messages_to_send:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                fail_silently=True,
            )
        except Exception as exc:
            if settings.DEBUG:
                print(f"Failed to send email to {recipient_list[0]}: {exc}")

    # Option 2 (Recommended for large courses): send_mass_mail
    # from django.core.mail import send_mass_mail
    # try:
    #     send_mass_mail(messages_to_send, fail_silently=True)
    # except Exception as exc:
    #     if settings.DEBUG:
    #         print(f"Mass email failed: {exc}")


# Optional: Celery task version (recommended for production)
try:
    from celery import shared_task

    @shared_task
    def task_notify_students_of_announcement(announcement_id: int) -> None:
        """
        Celery task to asynchronously send announcement emails.
        """
        try:
            ann = Announcement.objects.get(id=announcement_id)
        except Announcement.DoesNotExist:
            return

        notify_students_of_announcement(ann)

except ImportError:
    # Celery not installed — define a no-op fallback
    def task_notify_students_of_announcement(announcement_id: int) -> None:
        pass

# @login_required
# def generate_certificate(request, course_id):
#     course = get_object_or_404(Course, id=course_id)

#     if not UserProgress.objects.filter(user=request.user, course=course, completed=True).exists():
#         return HttpResponse("Complete the course first!")

#     # Create certificate record if doesn't exist
#     Certificate.objects.get_or_create(user=request.user, course=course)

#     # Generate PDF
#     response = HttpResponse(content_type='application/pdf')
#     response['Content-Disposition'] = f'attachment; filename="{course.title}_certificate.pdf"'

#     pdf = canvas.Canvas(response)
#     pdf.setFont("Helvetica-Bold", 28)
#     pdf.drawCentredString(300, 700, "Certificate of Completion")

#     pdf.setFont("Helvetica", 20)
#     pdf.drawCentredString(300, 650, f"This certificate is awarded to:")

#     pdf.setFont("Helvetica-Bold", 26)
#     pdf.drawCentredString(300, 600, request.user.get_full_name())

#     pdf.setFont("Helvetica", 18)
#     pdf.drawCentredString(300, 550, f"For successfully completing:")
#     pdf.setFont("Helvetica-Bold", 22)
#     pdf.drawCentredString(300, 520, course.title)

#     pdf.showPage()
#     pdf.save()
#     return response
