from pydantic import BaseModel


class AgentStatusOut(BaseModel):
    enabled: bool
    status: str
    service: str
