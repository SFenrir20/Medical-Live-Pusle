"""Bounded OCR preview. A human must review the text before creating a contact."""
import asyncio
import io
import warnings
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from .access import require_role
from .classify import phones_in

router = APIRouter(prefix='/v1/contacts')
care = require_role('care')


def recognize(data):
    import pytesseract
    from PIL import Image, UnidentifiedImageError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width * image.height > 12_000_000:
                    raise HTTPException(422, 'Usa una captura PNG, JPG o WebP de hasta 12 megapíxeles.')
                image.load()
                text = pytesseract.image_to_string(image.convert('RGB'), lang='spa+eng', timeout=20)
        return {'text': text[:10000], 'phones': phones_in(text), 'requires_review': True}
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'No se pudo leer la imagen.') from None
    except pytesseract.TesseractNotFoundError:
        raise HTTPException(503, 'El motor OCR no está instalado en este servidor.') from None
    except RuntimeError:
        raise HTTPException(422, 'La captura tardó demasiado; recorta el área del comentario.') from None


@router.post('/ocr')
async def preview(file: Annotated[UploadFile, File()], user=Depends(care)):
    try:
        data = await file.read(5 * 1024 * 1024 + 1)
    finally:
        await file.close()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, 'La captura debe pesar como máximo 5 MB.')
    return await asyncio.to_thread(recognize, data)
