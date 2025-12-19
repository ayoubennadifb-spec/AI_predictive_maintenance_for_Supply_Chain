from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from api.models import UserProfile


class Command(BaseCommand):
    help = "Create or update a super-admin user who can manage other users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="superadmin",
            help="Username for the super-admin (default: superadmin)",
        )
        parser.add_argument(
            "--password",
            default="SuperAdmin123!",
            help="Password for the super-admin (default: SuperAdmin123!)",
        )
        parser.add_argument(
            "--email",
            default="",
            help="Email for the super-admin (optional)",
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        email = options["email"] or None

        User = get_user_model()

        # Many custom User models enforce email as non-null, so always pass a non-empty value.
        effective_email = email or f"{username}@example.com"

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": effective_email},
        )

        # Ensure proper flags and password
        user.is_staff = True
        user.is_superuser = True
        if password:
            user.set_password(password)
        if email:
            user.email = email
        user.save()

        profile, profile_created = UserProfile.objects.get_or_create(
            user=user,
            defaults={"role": UserProfile.ROLE_SUPERADMIN, "nom": "Super Admin"},
        )
        if not profile_created and profile.role != UserProfile.ROLE_SUPERADMIN:
            profile.role = UserProfile.ROLE_SUPERADMIN
            profile.save(update_fields=["role"])

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Super-admin user '{username}' created with role 'superadmin'."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Super-admin user '{username}' updated (role ensured to 'superadmin')."
                )
            )

        self.stdout.write(
            self.style.NOTICE(
                "Credentials - "
                f"username: {username}, password: {password} "
                "(change these in production)."
            )
        )


