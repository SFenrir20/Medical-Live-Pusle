"""Reads the appointment confirmation the appointments centre sends to a patient:

    Muy bien, le envío los datos de su cita:
    Paciente: Camila Sánchez
    Fecha: 1-8
    Hora: 3pm a 4pm
    Sede: SJM
    Dirección: …

Pure functions (no database): the text goes in, what the rules need comes out. A message counts
as a confirmation only when it has the labels Sede, Fecha and Hora, so an ordinary sentence that
mentions a branch never moves anyone."""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

LABEL = re.compile(r'^[^\w\n]*\s*(paciente|fecha|hora|sede)\s*:\s*(.+?)\s*$', re.IGNORECASE | re.MULTILINE)
MONTHS = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7,
          'agosto': 8, 'setiembre': 9, 'septiembre': 9, 'octubre': 10, 'noviembre': 11,
          'diciembre': 12}
NUMERIC_DATE = re.compile(r'(\d{1,2})\s*[-/.]\s*(\d{1,2})(?:\s*[-/.]\s*(\d{2,4}))?')
WORDED_DATE = re.compile(r'(\d{1,2})\s*(?:de\s+)?(' + '|'.join(MONTHS) + r')(?:\s+(?:de\s+)?(\d{4}))?',
                         re.IGNORECASE)
TIME = re.compile(r'(\d{1,2})(?::(\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?(?![\d])', re.IGNORECASE)


def plain(text: str) -> str:
    """Lower case, no accents or punctuation: how a branch name is compared."""
    folded = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', ' ', folded.lower()).strip()


@dataclass
class Appointment:
    patient: str | None
    site_text: str
    date_text: str
    hour_text: str
    day: date | None
    start: time | None

    @property
    def label(self) -> str:
        return f'{self.date_text} · {self.hour_text}'[:80]


def _meridiem(token: str | None) -> str | None:
    return token.replace('.', '').replace(' ', '').lower() if token else None


def parse_hour(text: str) -> time | None:
    """The start of "3pm a 4pm", "11 a 12pm", "15:30", "9:00 am - 10:00 am"."""
    found = [(int(h), int(m or 0), _meridiem(mer)) for h, m, mer in TIME.findall(text)
             if int(h) <= 24 and int(m or 0) < 60]
    if not found:
        return None
    hour, minute, meridiem = found[0]
    if meridiem is None and len(found) > 1 and found[1][2] and hour < 13:
        later = found[1]
        pm = (hour % 12) + 12
        later_hour = (later[0] % 12) + (12 if later[2] == 'pm' else 0)
        meridiem = 'pm' if pm <= later_hour else 'am'
    if meridiem == 'pm' and hour < 12:
        hour += 12
    elif meridiem == 'am' and hour == 12:
        hour = 0
    elif meridiem is None and 1 <= hour <= 7:
        hour += 12                      # a clinic does not attend at 3 in the morning
    return time(hour % 24, minute) if hour <= 24 else None


def parse_day(text: str, today: date) -> date | None:
    """"1-8", "01/08", "1 de agosto", "hoy", "mañana". The year is the next one that is not past."""
    plain_text = plain(text)
    if plain_text.startswith('hoy'):
        return today
    if plain_text.startswith('manana'):
        return today + timedelta(days=1)
    day = month = year = None
    worded = WORDED_DATE.search(text.lower())
    if worded:
        day, month = int(worded.group(1)), MONTHS[worded.group(2).lower()]
        year = int(worded.group(3)) if worded.group(3) else None
    else:
        numeric = NUMERIC_DATE.search(text)
        if numeric:
            day, month = int(numeric.group(1)), int(numeric.group(2))
            if numeric.group(3):
                year = int(numeric.group(3))
                year += 2000 if year < 100 else 0
    if day is None or not (1 <= (month or 0) <= 12):
        return None
    try:
        if year is not None:
            return date(year, month, day)
        candidate = date(today.year, month, day)
        return candidate if candidate >= today - timedelta(days=60) else date(today.year + 1, month, day)
    except ValueError:
        return None


def parse_appointment(text: str, today: date) -> Appointment | None:
    fields = {}
    for name, value in LABEL.findall(text or ''):
        fields.setdefault(name.lower(), value.strip())
    if not {'sede', 'fecha', 'hora'} <= fields.keys():
        return None
    return Appointment(
        patient=fields.get('paciente'), site_text=fields['sede'], date_text=fields['fecha'],
        hour_text=fields['hora'], day=parse_day(fields['fecha'], today),
        start=parse_hour(fields['hora']))


def starts_at(appointment: Appointment, tz) -> datetime | None:
    """When the appointment starts (timezone-aware), or None if the date is not understood."""
    if appointment.day is None:
        return None
    return datetime.combine(appointment.day, appointment.start or time(0, 0), tzinfo=tz)
