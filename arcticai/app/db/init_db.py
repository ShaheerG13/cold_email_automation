from __future__ import annotations

from arcticai.app.db.session import engine
from arcticai.app.models.base import Base
from arcticai.app.utils.debug_log import dlog

# Ensure model modules are imported so metadata is populated.
from arcticai.app.models.company import Company  # noqa: F401
from arcticai.app.models.contact import Contact  # noqa: F401
from arcticai.app.models.outreach import Outreach  # noqa: F401
from arcticai.app.models.user import User  # noqa: F401


async def init_db() -> None:
    # region agent log
    dlog(
        location="arcticai/app/db/init_db.py:init_db",
        message="init_db_start",
        data={},
        run_id="pre-fix",
        hypothesis_id="H2",
    )
    # endregion
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # region agent log
    dlog(
        location="arcticai/app/db/init_db.py:init_db",
        message="init_db_done",
        data={},
        run_id="pre-fix",
        hypothesis_id="H2",
    )
    # endregion

