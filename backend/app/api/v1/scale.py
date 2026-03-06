from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.services.scale_service import scale_service
from pydantic import BaseModel

router = APIRouter(prefix="/scale", tags=["Weighing Scale"])


class WeightRequest(BaseModel):
    expected_weight: float = 10.0


@router.post("/read-weight")
async def read_weight(data: WeightRequest, current_user=Depends(get_current_user)):
    """Read weight from connected scale or simulation"""
    result = await scale_service.read_weight(data.expected_weight)
    return result


@router.get("/status")
async def scale_status(current_user=Depends(get_current_user)):
    """Get scale connection status"""
    return await scale_service.get_status()
