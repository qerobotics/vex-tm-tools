"""Pydantic schemas mirroring `backend.models.timer` (plan §8)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TimerInstanceBase(BaseModel):
    entity_id: str = Field(..., max_length=100)
    display_name: str = Field(..., max_length=150)
    field_set_id: int
    field_id: int
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    # Wave 2b addition — see backend/models/timer.py docstring. Appendix A.3:
    # "Countdown duration ... Configurable per Timer instance in the UI (a
    # number field, in seconds). Not inside automation YAML."
    duration_s: int = Field(default=120, ge=1, description="Countdown duration in seconds.")


class TimerInstanceCreate(TimerInstanceBase):
    pass


class TimerInstanceUpdate(BaseModel):
    display_name: str | None = None
    field_set_id: int | None = None
    field_id: int | None = None
    tags: list[str] | None = None
    enabled: bool | None = None
    duration_s: int | None = Field(default=None, ge=1)
    # Appendix B.8: "Regeneration ... Creates a new HMAC using a per-instance
    # nonce stored in Postgres. Old tokens are immediately invalid." Setting
    # this true on a PUT rotates `token_nonce`, invalidating the previously
    # issued teleprompter link.
    regenerate_token: bool = False


class TimerInstanceRead(TimerInstanceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    # Computed (not an ORM column name) — the current HMAC token for this
    # instance's teleprompter link, per Appendix B.8. Populated by the
    # router from `entity_id` + `token_nonce`; `token_nonce` itself is never
    # serialized to clients.
    prompter_token: str = Field(
        default="", description="Current HMAC token for /prompter/<entity_id>?token=..."
    )


class PrompterCueBase(BaseModel):
    timer_entity_id: str = Field(..., max_length=100)
    content: str
    type: str = Field(default="script", max_length=30)
    sort_order: int = 0
    is_active: bool = True


class PrompterCueCreate(PrompterCueBase):
    pass


class PrompterCueUpdate(BaseModel):
    content: str | None = None
    type: str | None = Field(default=None, max_length=30)
    sort_order: int | None = None
    is_active: bool | None = None


class PrompterCueRead(PrompterCueBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by: str | None = None
    created_at: datetime
