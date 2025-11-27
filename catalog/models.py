from django.db import models
from django.contrib.auth.models import User

class Student(models.Model):
    name = models.CharField(max_length=200)

class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Course(models.Model):
    LEVEL_CHOICES = [
        ('Beginner', 'Beginner'),
        ('Intermediate', 'Intermediate'),
        ('Advanced', 'Advanced'),
    ]

    DURATION_CHOICES = [
        ('4 weeks', '4 weeks'),
        ('8 weeks', '8 weeks'),
        ('12 weeks', '12 weeks'),
        ('16 weeks', '16 weeks'),
        ('20 weeks', '20 weeks'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    instructor = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, related_name='courses', on_delete=models.CASCADE)
    skills = models.CharField(max_length=500, blank=True)

    duration = models.CharField(
        max_length=20,
        choices=DURATION_CHOICES,
        default='4 weeks'
    )

    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='Beginner')
    price = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rating = models.FloatField(default=4.8)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Review(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(default=1)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.course.title} ({self.rating})"

class Enrollment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    grade = models.CharField(max_length=20, blank=True, null=True)
    progress = models.FloatField(default=0.0)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user.username} enrolled in {self.course.title}"

class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    video = models.FileField(upload_to='lesson_videos/', blank=True, null=True)
    
    # Add this field for proper ordering
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']  # This makes .all() automatically sorted!

    def __str__(self):
        return f"{self.title} ({self.course.title})"

class LessonProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'lesson')

    def __str__(self):
        return f"{self.user.username} - {self.lesson.title} - {'Completed' if self.completed else 'Incomplete'}"

class SupportTicket(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ticket from {self.user.username}: {self.subject}"

class Post(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='posts')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Post by {self.user.username} on {self.course.title}"

class Reply(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reply by {self.user.username}"

class Quiz(models.Model):
    EASY = 'Easy'
    MEDIUM = 'Medium'
    HARD = 'Hard'
    DIFFICULTY_LEVELS = [
        (EASY, 'Easy'),
        (MEDIUM, 'Medium'),
        (HARD, 'Hard'),
    ]

    course = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='quizzes')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    max_marks = models.PositiveIntegerField(default=100)
    time_limit_minutes = models.PositiveIntegerField(default=0, help_text="Time limit in minutes. 0 = no limit")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_LEVELS, default=MEDIUM)
    is_published = models.BooleanField(default=False)
    question_count = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']  # newest quizzes first
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"

    def __str__(self):
        return f"{self.title} - {self.course.title}"

    def is_timed(self):
        return self.time_limit_minutes > 0

class Question(models.Model):
    MULTIPLE_CHOICE = 'MCQ'
    TRUE_FALSE = 'TF'
    SHORT_ANSWER = 'SA'
    QUESTION_TYPES = [
        (MULTIPLE_CHOICE, 'Multiple Choice'),
        (TRUE_FALSE, 'True/False'),
        (SHORT_ANSWER, 'Short Answer'),
    ]

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    question_type = models.CharField(max_length=3, choices=QUESTION_TYPES, default=MULTIPLE_CHOICE)
    option1 = models.CharField(max_length=255, blank=True, null=True)
    option2 = models.CharField(max_length=255, blank=True, null=True)
    option3 = models.CharField(max_length=255, blank=True, null=True)
    option4 = models.CharField(max_length=255, blank=True, null=True)
    correct_option = models.PositiveSmallIntegerField(choices=[(1,1),(2,2),(3,3),(4,4)], null=True, blank=True)
    marks = models.PositiveIntegerField(default=1)
    difficulty = models.CharField(max_length=10, choices=Quiz.DIFFICULTY_LEVELS, default=Quiz.MEDIUM)
    is_best_question = models.BooleanField(default=False, help_text="Mark this question as one of the best questions in the quiz")
    
    def __str__(self):
        return f"{self.text[:50]}..."
    
    def get_options(self):
        """Return list of (number, text) tuples for available options"""
        options = []
        for i in range(1, 5):
            opt_text = getattr(self, f'option{i}', None)
            if opt_text:
                options.append((i, opt_text.strip()))
        return options


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=200)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.text} ({'Correct' if self.is_correct else 'Incorrect'})"


# class Question(models.Model):
#     quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
#     text = models.CharField(max_length=500)
#     option1 = models.CharField(max_length=200)
#     option2 = models.CharField(max_length=200)
#     option3 = models.CharField(max_length=200)
#     option4 = models.CharField(max_length=200)
#     correct_option = models.IntegerField(choices=[(1,'Option 1'),(2,'Option 2'),(3,'Option 3'),(4,'Option 4')])
#     max_score = models.PositiveIntegerField(default=1)
#     difficulty = models.CharField(max_length=1, choices=Quiz.DIFFICULTY_CHOICES, default='M')
#     is_best_question = models.BooleanField(default=False, help_text="Mark this question as one of the best questions in the quiz")

    def __str__(self):
        return f"Q: {self.text}"

# class Skill(models.Model):
#     name = models.CharField(max_length=100)

#     def __str__(self):
#         return self.name

class QuizResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    score = models.IntegerField()
    total_marks = models.FloatField()
    taken_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.quiz.title} - {self.score}"


class Bundle(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    courses = models.ManyToManyField(Course)
    price = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self):
        return self.name

class BundleOrder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE)
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.bundle.name} - {'Paid' if self.paid else 'Unpaid'}"

class LessonNote(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    note = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'lesson')

class Announcement(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='announcements')
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)


    def __str__(self):
        return f"{self.title} ({self.course.title})"

class LiveClass(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='live_classes')
    topic = models.CharField(max_length=200)
    start_time = models.DateTimeField()
    zoom_link = models.URLField(blank=True, null=True)

    def __str__(self):
        return f"{self.topic} - {self.course.title}"

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # Existing fields
    points = models.IntegerField(default=0)
    badge = models.CharField(max_length=50, blank=True, null=True)

    # New fields
    complete_count = models.IntegerField(default=0)
    reviews = models.IntegerField(default=0)
    progress_percentage = models.FloatField(default=0.0)

    # Level system
    user_level = models.IntegerField(default=1)
    user_xp = models.IntegerField(default=0)
    user_level_xp = models.IntegerField(default=100)  # XP required for next level

    def update_badge(self):
        if self.points >= 1000:
            self.badge = "Gold"
        elif self.points >= 500:
            self.badge = "Silver"
        elif self.points >= 100:
            self.badge = "Bronze"
        else:
            self.badge = None
        self.save()

    def update_level(self):
        while self.user_xp >= self.user_level_xp:
            self.user_xp -= self.user_level_xp
            self.user_level += 1
            self.user_level_xp = int(self.user_level_xp * 1.5)
        self.save()

    def __str__(self):
        return f"{self.user.username}'s Profile"


class LessonBookmark(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'lesson')

class Certificate(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'course')
