"""Who is on a LIVE: the TikToker writes her code in the live title (e.g. "Cirugías A1").

A code counts only as a whole word and only if it belongs to a known TikToker, so ordinary
words never match. Exactly one code identifies the responsible; no code, or several different
ones, identify nobody (the live stays "Sin asignar" rather than guessing)."""
import re

WORD = re.compile(r'(?<![A-Za-z0-9])([A-Za-z][0-9]{1,2})(?![A-Za-z0-9])')
MAX_TITLE = 200


def clean_title(title) -> str | None:
    if not isinstance(title, str):
        return None
    value = ' '.join(title.split())[:MAX_TITLE]
    return value or None


def find_codes(title, known) -> list[str]:
    """Distinct known codes in the title, in order of appearance (case-insensitive)."""
    found: list[str] = []
    for match in WORD.finditer(title or ''):
        code = match.group(1).upper()
        if code in known and code not in found:
            found.append(code)
    return found


def resolve(title, by_code: dict[str, str]):
    """-> (tiktoker_id | None, 'matched' | 'none' | 'ambiguous')"""
    codes = find_codes(title, by_code.keys())
    if len(codes) == 1:
        return by_code[codes[0]], 'matched'
    return None, ('ambiguous' if codes else 'none')


def note_for(title, by_code: dict[str, str], responsible_id) -> str | None:
    """Why a live has no (or an uncertain) responsible, for people to fix at the source."""
    if responsible_id:
        return None
    if not title:
        return 'sin_titulo'
    return {'matched': None, 'none': 'titulo_sin_codigo',
            'ambiguous': 'titulo_con_varios_codigos'}[resolve(title, by_code)[1]]
