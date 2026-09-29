from app.db.base import Base
from app.db.models.appeal import (
    Appeal,
    AppealCategory,
    AppealMessage,
    AppealPriority,
    AppealStatus,
    Notification,
)
from app.db.models.consent import (
    AuditEvent,
    ConsentPurpose,
    ConsentSource,
    OutboxMessage,
    PolicyDocument,
    ProcessedUpdate,
    UserConsent,
)
from app.db.models.school import (
    ClassGroup,
    GuardianLink,
    Organization,
    Student,
    TeacherAssignment,
)
from app.db.models.tutor import (
    MessageAuthor,
    ParentLink,
    Task,
    TaskMessage,
    TaskStatus,
    TaskSubject,
)
from app.db.models.user import AuthSession, User, UserRole

__all__ = [
    "Appeal",
    "AppealCategory",
    "AppealMessage",
    "AppealPriority",
    "AppealStatus",
    "AuditEvent",
    "AuthSession",
    "Base",
    "ClassGroup",
    "ConsentPurpose",
    "ConsentSource",
    "GuardianLink",
    "MessageAuthor",
    "Notification",
    "Organization",
    "OutboxMessage",
    "ParentLink",
    "PolicyDocument",
    "ProcessedUpdate",
    "Student",
    "Task",
    "TaskMessage",
    "TaskStatus",
    "TaskSubject",
    "TeacherAssignment",
    "User",
    "UserConsent",
    "UserRole",
]
