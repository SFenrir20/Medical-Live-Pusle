from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..modules.analytics.api import router as analytics_router
from ..modules.analytics.ocr import router as ocr_router
from ..modules.automation.api import router as automation_router
from ..modules.chat.api import router as chat_router
from ..modules.crm.api import router as crm_router
from ..modules.crm.automation_api import router as auto_rules_router
from ..modules.crm.pipelines import router as pipelines_router
from ..modules.crm.sites import router as sites_router
from ..modules.identity.api import router as identity_router
from ..modules.social_live.alerts_api import router as alerts_router
from ..modules.social_live.api import marketing as marketing_router
from ..modules.social_live.api import social as social_live_router
from ..modules.social_live.audience import router as audience_router
from ..modules.social_live.distribution import router as presence_router
from ..modules.social_live.leads import router as leads_router
from ..modules.tiktok_oauth.api import router as tiktok_oauth_router
from ..modules.whatsapp.api import router as whatsapp_router
from ..shared.auth import get_current_user
from ..shared.config import settings

app = FastAPI(title="Medical Social Pulse API", version="0.3.0")
app.include_router(analytics_router)

app.include_router(ocr_router)
app.include_router(identity_router)
app.include_router(social_live_router)
app.include_router(marketing_router)
app.include_router(leads_router)
app.include_router(alerts_router)
app.include_router(audience_router)
app.include_router(presence_router)
app.include_router(chat_router)
app.include_router(whatsapp_router)
app.include_router(crm_router)
app.include_router(pipelines_router)
app.include_router(sites_router)
app.include_router(auto_rules_router)
app.include_router(automation_router)
app.include_router(tiktok_oauth_router)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["GET", "POST", "PUT", "PATCH"],
                   allow_headers=["Authorization", "Content-Type"])


@app.get("/v1/me")
def me(user=Depends(get_current_user)):
    return user


@app.get("/health")
async def health():
    return {"ok": True}
