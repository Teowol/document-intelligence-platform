from django.contrib.auth.models import AbstractUser, Group
from django.db import models
from django.utils.translation import gettext_lazy as _


class CustomUser(AbstractUser):
    """
    Custom User model with email as the primary identifier.

    Roles (RBAC, Phase 2):
        admin  — full control (staff-level actions, manage everything)
        editor — upload and delete documents
        viewer — read-only access
    """

    class Roles(models.TextChoices):
        ADMIN = "admin", _("Admin")
        EDITOR = "editor", _("Editor")
        VIEWER = "viewer", _("Viewer")

    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=10,
        choices=Roles.choices,
        default=Roles.VIEWER,
        db_index=True,
    )
    bio = models.TextField(blank=True, default="")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    @property
    def is_admin_role(self):
        """Admin role OR Django superuser/staff counts as admin."""
        return self.role == self.Roles.ADMIN or self.is_superuser

    def save(self, *args, **kwargs):
        """Keep the Django Group membership in sync with the role field."""
        old_role = None
        if self.pk is not None:
            old_role = (
                CustomUser.objects.filter(pk=self.pk)
                .values_list("role", flat=True)
                .first()
            )
        super().save(*args, **kwargs)
        if old_role is None or old_role != self.role:
            self._sync_role_group()

    def _sync_role_group(self):
        """Mirror the role choice into the matching auth Group."""
        group, _ = Group.objects.get_or_create(name=f"role_{self.role}")
        role_group_names = {f"role_{r}" for r, _ in self.Roles.choices}
        self.groups.remove(*self.groups.filter(name__in=role_group_names))
        self.groups.add(group)
