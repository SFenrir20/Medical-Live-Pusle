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


def test_phone_normalization_and_interest_negation():
    assert phones_in('mi número 987 654 321 y +51 987654321') == ['+51987654321']
    assert not phones_in('123456')
    assert interested_in('¿Cuánto cuesta? Quiero información')
    assert not interested_in('no me interesa esa operación')
    assert not interested_in('hola buenas noches')
