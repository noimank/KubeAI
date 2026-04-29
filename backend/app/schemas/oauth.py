from pydantic import BaseModel


class OAuthProviderResponse(BaseModel):
    name: str
    display_name: str


class OAuthAuthorizeResponse(BaseModel):
    authorization_url: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str
