from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_api_admin
from app.database import get_db
from app.models import SystemSetting, User


router = APIRouter(prefix="/settings", tags=["settings"])
DEFAULT_SYSTEM_NAME = "人事考核管理系统"


class SystemSettingsPayload(BaseModel):
    system_name: str


def current_system_name(db: Session) -> str:
    setting = db.get(SystemSetting, "system_name")
    return setting.value if setting and setting.value.strip() else DEFAULT_SYSTEM_NAME


@router.get("", response_model=SystemSettingsPayload)
def get_settings(db: Session = Depends(get_db)) -> SystemSettingsPayload:
    return SystemSettingsPayload(system_name=current_system_name(db))


@router.put("", response_model=SystemSettingsPayload)
def update_settings(payload: SystemSettingsPayload, db: Session = Depends(get_db), _: User = Depends(require_api_admin)) -> SystemSettingsPayload:
    system_name = payload.system_name.strip()
    if not system_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="系统名称不能为空。")
    if len(system_name) > 80:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="系统名称不能超过 80 个字符。")
    setting = db.get(SystemSetting, "system_name")
    if setting:
        setting.value = system_name
    else:
        db.add(SystemSetting(key="system_name", value=system_name))
    db.commit()
    return SystemSettingsPayload(system_name=system_name)
