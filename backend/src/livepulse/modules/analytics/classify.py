"""Deterministic comment classification and phone extraction (no medical inference)."""
import re
import unicodedata

import phonenumbers

# People disguise numbers in comments ("985//857#968", "9*8*1*545*41*1"). A run of digits
# separated only by 1-3 symbols (never plain spaces, so dates and prices stay apart) is
# rejoined and kept only if it is exactly a Peruvian mobile: 9 digits starting with 9,
# optionally prefixed by 51.
OBFUSCATED = re.compile(r'(?<![\w])\d(?:\s?[^\w\s]{1,3}\s?\d+|\d)*(?![\w])')


def disguised_phones(text: str, region: str) -> set[str]:
    found = set()
    for match in OBFUSCATED.finditer(text):
        digits = re.sub(r'\D', '', match.group())
        if not re.fullmatch(r'(?:51)?9\d{8}', digits):
            continue
        try:
            number = phonenumbers.parse(digits if len(digits) == 9 else '+' + digits, region)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(number):
            found.add(phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164))
    return found


def phones_in(text: str, region='PE') -> list[str]:
    found = {phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
             for match in phonenumbers.PhoneNumberMatcher(text, region)
             if phonenumbers.is_valid_number(match.number)}
    return sorted(found | disguised_phones(text, region))


def interested_in(text: str) -> bool:
    value = ''.join(c for c in unicodedata.normalize('NFKD', text.lower())
                    if not unicodedata.combining(c))
    if re.search(r'\b(no me interesa|no quiero|no deseo)\b', value):
        return False
    return bool(re.search(
        r'\b(precio|costo|cuanto cuesta|informacion|informes|me interesa|quisiera|'
        r'quiero operarme|quiero una cita|agendar|cotizacion|requisitos|financiamiento)\b', value))
