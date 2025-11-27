from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission

class Command(BaseCommand):
    def handle(self, *args, **options):
        for g in ['Student', 'Instructor']:
            Group.objects.get_or_create(name=g)
        self.stdout.write("Groups created.")
