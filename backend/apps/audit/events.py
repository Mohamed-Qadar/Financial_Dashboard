"""Catalog of audit event types.

Only events that the system can actually emit are listed. Each milestone adds the events it
introduces (e.g. authentication events in 2.2, role changes in 2.4). Names are stable
identifiers: never rename or reuse one, because stored rows refer to them.
"""

from django.db import models


class AuditEvent(models.TextChoices):
    DB_RUNTIME_ROLE_ENSURED = (
        "security.db_runtime_role_ensured",
        "Runtime database role created or updated",
    )
    # Authentication (milestone 2.2)
    LOGIN_SUCCEEDED = "auth.login_succeeded", "Login succeeded"
    LOGIN_FAILED = "auth.login_failed", "Login failed"
    LOGIN_THROTTLED = "auth.login_throttled", "Login attempts rate-limited"
    LOGOUT = "auth.logout", "Logout"
    PASSWORD_CHANGED = "auth.password_changed", "Password changed"
    PASSWORD_CHANGE_FAILED = "auth.password_change_failed", "Password change failed"
    PASSWORD_CHANGE_THROTTLED = (
        "auth.password_change_throttled",
        "Password change attempts rate-limited",
    )
    PASSWORD_RESET_REQUESTED = "auth.password_reset_requested", "Password reset requested"
    PASSWORD_RESET_THROTTLED = (
        "auth.password_reset_throttled",
        "Password reset requests rate-limited",
    )
    PASSWORD_RESET_EMAIL_FAILED = (
        "auth.password_reset_email_failed",
        "Password reset e-mail could not be sent",
    )
    PASSWORD_RESET_COMPLETED = "auth.password_reset_completed", "Password reset completed"
    PASSWORD_RESET_FAILED = "auth.password_reset_failed", "Password reset failed"
    # Tenancy (milestone 2.3a)
    COMPANY_SELECTED = "tenancy.company_selected", "Active company selected"
    COMPANY_ACCESS_DENIED = "tenancy.company_access_denied", "Company access denied"
    COMPANY_ACCESS_THROTTLED = (
        "tenancy.company_access_throttled",
        "Denied company access attempts rate-limited",
    )
    # Registration (milestone 2.3b)
    BUSINESS_REGISTERED = "tenancy.business_registered", "Business registered"
    MEMBERSHIP_CREATED = "tenancy.membership_created", "Membership created"
    REGISTRATION_FAILED = "tenancy.registration_failed", "Registration failed"
    REGISTRATION_THROTTLED = (
        "tenancy.registration_throttled",
        "Registration attempts rate-limited",
    )


class Outcome(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"
    DENIED = "denied", "Denied"


class ActorType(models.TextChoices):
    USER = "user", "User"
    SYSTEM = "system", "System"
    ANONYMOUS = "anonymous", "Anonymous"
