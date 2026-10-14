from types import SimpleNamespace

from livepulse.entrypoints.monitor import normalize
from livepulse.modules.analytics.classify import interested_in, phones_in


def test_provider_common_id_deduplicates_despite_receive_time():
    event = SimpleNamespace(common=SimpleNamespace(msg_id=123, create_time=1791400000),
                            user=SimpleNamespace(id=9, unique_id='ana', nickname='Ana'))
    first = normalize('comment', 'medical', 'room', event, 'hola')
    second = normalize('comment', 'medical', 'room', event, 'hola')
    assert first['event_id'] == second['event_id'] == 'medical:room:comment:123'
    assert first['payload']['user'] == '9'
    assert first['payload']['time_source'] == 'provider'


def test_disguised_phone_numbers_are_rejoined():
    assert phones_in('985//857#968') == ['+51985857968']
    assert phones_in('9*8*1*545*41*1') == ['+51981545411']
    assert phones_in('escríbeme al 9-8-5-8-5-7-9-6-8 porfa') == ['+51985857968']
    assert phones_in('mi cel: 985.857.968') == ['+51985857968']
    assert phones_in('+51 985//857//968') == ['+51985857968']
    # The same number written two ways is one contact.
    assert phones_in('985857968 o 985//857#968') == ['+51985857968']


def test_disguised_numbers_do_not_create_false_phones():
    for text in ['12/10/2026', 'cuesta S/ 1.500.000', '1*2*3*4', '10:30 a 11:45',
                 'el 15-10-2026 a las 987', '2026 2027 2028 2029',
                 '12/10/2026 985857968 de 31/12/2026']:
        assert phones_in(text) in ([], ['+51985857968']), text
    assert phones_in('12/10/2026') == []
    assert phones_in('cuesta S/ 1.500.000') == []
    assert phones_in('Llámame 9 de la mañana') == []


def test_phone_normalization_and_interest_negation():
    assert phones_in('mi número 987 654 321 y +51 987654321') == ['+51987654321']
    assert not phones_in('123456')
    assert interested_in('¿Cuánto cuesta? Quiero información')
    assert not interested_in('no me interesa esa operación')
    assert not interested_in('hola buenas noches')
