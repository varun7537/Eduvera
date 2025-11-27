from django import forms
from .models import Review, SupportTicket, Post, Reply, LessonNote, Announcement

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']

class SupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ['subject', 'message']

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['content']

class ReplyForm(forms.ModelForm):
    class Meta:
        model = Reply
        fields = ['content']

class LessonNoteForm(forms.ModelForm):
    class Meta:
        model = LessonNote
        fields = ['note']
        widgets = {
            'note': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Write your note...'})
        }

class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'message']
