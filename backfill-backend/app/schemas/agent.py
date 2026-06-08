from pydantic import BaseModel


class AgentStatusOut(BaseModel):
    enabled: bool
    status: str
    service: str
    sms_provider: str
    sms_mode: str
    mock_sms_enabled: bool
