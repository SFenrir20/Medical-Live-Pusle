from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

security = HTTPBearer(auto_error=False)


async def get_current_user(credentials=Depends(security)):
    # TODO: validar JWT real y cargar usuario + cuentas autorizadas.
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No auth")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Autenticación pendiente de implementar; no se aceptan tokens de demostración.",
    )
