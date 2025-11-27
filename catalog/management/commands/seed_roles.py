# catalog/management/commands/seed_roles.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

class Command(BaseCommand):
    help = "Create default user groups"

    def handle(self, *args, **options):
        for name in ["Student", "Instructor"]:
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("Groups created: Student, Instructor"))
