"""Deterministic comment classification and phone extraction (no medical inference)."""
import re
import unicodedata

import phonenumbers


def phones_in(text: str, region='PE') -> list[str]:
    return sorted({phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
                   for match in phonenumbers.PhoneNumberMatcher(text, region)
                   if phonenumbers.is_valid_number(match.number)})


def interested_in(text: str) -> bool:
    value = ''.join(c for c in unicodedata.normalize('NFKD', text.lower())
                    if not unicodedata.combining(c))
    if re.search(r'\b(no me interesa|no quiero|no deseo)\b', value):
        return False
    return bool(re.search(
        r'\b(precio|costo|cuanto cuesta|informacion|informes|me interesa|quisiera|'
        r'quiero operarme|quiero una cita|agendar|cotizacion|requisitos|financiamiento)\b', value))
