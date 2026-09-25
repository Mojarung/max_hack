"""Импорт всех моделей, чтобы они попали в Base.metadata."""

from domovoy.modules.events.models import Event, EventComment, EventParticipant
from domovoy.modules.issues.models import Issue, IssueUpdate, IssueVote
from domovoy.modules.market.models import Listing
from domovoy.modules.misc_models import (
    Alert,
    Announcement,
    Document,
    McpServer,
    MockChatMessage,
    ModerationLog,
    Shelter,
    UserAchievement,
)
from domovoy.modules.users.models import House, Membership, Organization, PointsLog, User

__all__ = [
    "Alert",
    "Announcement",
    "Document",
    "Event",
    "EventComment",
    "EventParticipant",
    "House",
    "Issue",
    "IssueUpdate",
    "IssueVote",
    "Listing",
    "McpServer",
    "Membership",
    "MockChatMessage",
    "ModerationLog",
    "Organization",
    "PointsLog",
    "Shelter",
    "User",
    "UserAchievement",
]
