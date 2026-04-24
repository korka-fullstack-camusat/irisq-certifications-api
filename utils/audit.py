from datetime import datetime
from typing import Any, Optional
from database import get_database


async def log_action(
    action: str,
    resource_type: str,
    resource_id: str,
    user_email: str,
    user_role: str,
    user_name: Optional[str] = None,
    resource_label: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    try:
        db = get_database()
        await db["audit_logs"].insert_one({
            "timestamp": datetime.utcnow(),
            "user_email": user_email,
            "user_role": user_role,
            "user_name": user_name or user_email,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "resource_label": resource_label or resource_id,
            "details": details or {},
        })
    except Exception as e:
        print(f"[AUDIT] Failed to log action '{action}': {e}")
