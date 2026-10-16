import uuid
from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import created_at, pk

# Fixed id for the single tenant the MVP runs as, so seeds and requests agree
# without a lookup.
DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = created_at()
