# catalog/signals.py
from django.contrib.auth.models import Group, User
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Profile

@receiver(post_save, sender=User)
def add_new_user_to_student_group(sender, instance, created, **kwargs):
    if created:
        try:
            student_group, _ = Group.objects.get_or_create(name="Student")
            instance.groups.add(student_group)
        except Exception:
            pass

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
