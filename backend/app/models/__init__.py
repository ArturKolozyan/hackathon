from sqlalchemy.orm import configure_mappers

from app.models.assistant import AssistantAction, AssistantMessage
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.budget import Budget
from app.models.delivery import NotificationDelivery
from app.models.email_code import EmailCode
from app.models.invite import TeamInvite
from app.models.login_attempt import LoginAttempt
from app.models.occurrence import PaymentOccurrence
from app.models.recurring import RecurringPayment
from app.models.session import AuthSession
from app.models.team import Membership, Team
from app.models.telegram import TelegramBot, TelegramIntegration, TelegramLinkToken
from app.models.user import User

configure_mappers()

__all__ = [
    "AssistantAction",
    "AssistantMessage",
    "AuditLog",
    "AuthSession",
    "Base",
    "Budget",
    "EmailCode",
    "LoginAttempt",
    "Membership",
    "NotificationDelivery",
    "PaymentOccurrence",
    "RecurringPayment",
    "Team",
    "TeamInvite",
    "TelegramBot",
    "TelegramIntegration",
    "TelegramLinkToken",
    "User",
]
