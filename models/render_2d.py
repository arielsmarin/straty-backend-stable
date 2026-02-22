from pydantic import BaseModel
from typing import Dict, Any, Optional


class Render2DRequest(BaseModel):
    client: str
    scene: str
    selection: Dict[str, Any]
    buildString: Optional[str] = None  # opcional, backend calcula se não vier