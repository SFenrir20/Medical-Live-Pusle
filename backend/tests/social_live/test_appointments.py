"""Reading the appointment confirmation the appointments centre sends: what counts as one, the
branch, the date and the hour in the ways they are written."""
from datetime import date, time

import pytest

from livepulse.modules.crm.appointments import parse_appointment, parse_day, parse_hour, plain

TODAY = date(2026, 7, 20)
SAMPLE = """Muy bien, le envío los datos de su cita:
🫶🏽Paciente: Camila Sánchez
🗓️Fecha: 1-8
🕐Hora: 3pm a 4pm
📌Sede: SJM
📌Dirección: Clínica Sagrada Familia del Sur

Av. Miguel Iglesias No 625"""


def test_the_real_message_is_understood():
    found = parse_appointment(SAMPLE, TODAY)
    assert found is not None
    assert (found.patient, found.site_text, found.date_text, found.hour_text) == (
        'Camila Sánchez', 'SJM', '1-8', '3pm a 4pm')
    assert found.day == date(2026, 8, 1) and found.start == time(15, 0)
    assert found.label == '1-8 · 3pm a 4pm'


@pytest.mark.parametrize('text', [
    'Nuestra sede de SJM atiende de 9 a 5',                 # a sentence, not a confirmation
    'Fecha: 1-8\nHora: 3pm',                                  # no branch
    'Sede: SJM\nHora: 3pm',                                   # no date
    'Sede: SJM\nFecha: 1-8',                                  # no hour
    '', 'hola',
])
def test_only_a_full_confirmation_counts(text):
    assert parse_appointment(text, TODAY) is None


@pytest.mark.parametrize('text, expected', [
    ('3pm a 4pm', time(15, 0)), ('11 a 12pm', time(11, 0)), ('9:30 am', time(9, 30)),
    ('15:00', time(15, 0)), ('3 a 4pm', time(15, 0)), ('5pm', time(17, 0)),
    ('10 am a 11 am', time(10, 0)), ('2', time(14, 0)), ('12 pm', time(12, 0)),
    ('12 am', time(0, 0)), ('8:15', time(8, 15)), ('a la tarde', None),
])
def test_the_start_hour_in_every_way_it_is_written(text, expected):
    assert parse_hour(text) == expected


@pytest.mark.parametrize('text, expected', [
    ('1-8', date(2026, 8, 1)), ('01/08', date(2026, 8, 1)), ('1-8-2026', date(2026, 8, 1)),
    ('viernes 1 de agosto', date(2026, 8, 1)), ('3 de octubre', date(2026, 10, 3)),
    ('hoy', TODAY), ('Mañana', date(2026, 7, 21)),
    ('5-1', date(2027, 1, 5)),               # January already went by: next year
    ('31-2', None), ('pronto', None),
])
def test_the_date_in_every_way_it_is_written(text, expected):
    assert parse_day(text, TODAY) == expected


def test_branch_names_compare_without_accents_or_punctuation():
    assert plain('  San  Isidro / Lince ') == 'san isidro lince'
    assert plain('SJM.') == 'sjm' and plain('Ate Vitarte') == 'ate vitarte'
