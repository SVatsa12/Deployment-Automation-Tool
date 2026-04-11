"""
Create and resolve short links for deployment URLs.
"""
import secrets
import string
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.run import WorkflowRun
from app.models.short_link import ShortLink

_ALPHABET = string.ascii_lowercase + string.digits
_CODE_LEN = 7


def _public_base() -> str:
    return (settings.PUBLIC_BASE_URL or "http://127.0.0.1:8000").rstrip("/")


def _generate_unique_code(db: Session) -> str:
    for _ in range(48):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LEN))
        if not db.query(ShortLink).filter(ShortLink.code == code).first():
            return code
    raise RuntimeError("Could not allocate a unique short code")


def short_urls_for_run_ids(db: Session, run_ids: List[int]) -> Dict[int, str]:
    """Map workflow_run_id -> full short URL (e.g. https://host/r/abc12)."""
    if not run_ids:
        return {}
    rows = db.query(ShortLink).filter(ShortLink.workflow_run_id.in_(run_ids)).all()
    base = _public_base()
    return {r.workflow_run_id: f"{base}/r/{r.code}" for r in rows}


def ensure_short_link_for_run(db: Session, run: WorkflowRun) -> Optional[str]:
    """
    If the run has a deployment_url, ensure a ShortLink exists and return the public short URL.
    Updates target_url if the long URL changed.
    """
    url = (run.deployment_url or "").strip()
    if not url.startswith("http"):
        return None

    existing = db.query(ShortLink).filter(ShortLink.workflow_run_id == run.id).first()
    if existing:
        if existing.target_url != url:
            existing.target_url = url
            db.commit()
        return f"{_public_base()}/r/{existing.code}"

    code = _generate_unique_code(db)
    db.add(
        ShortLink(
            code=code,
            target_url=url,
            workflow_run_id=run.id,
        )
    )
    db.commit()
    return f"{_public_base()}/r/{code}"
