"""Chat core, flows, AI agent and broadcasts: permissions, the simulator, the safety policy of the
risky (mirror) channel, human takeover, opt-outs and the audit trail."""
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select

from livepulse.modules.analytics.models import UserRole
from livepulse.modules.automation import ai, engine, graph
from livepulse.modules.automation import broadcasts as broadcast_sender
from livepulse.modules.automation import models as am
from livepulse.modules.chat import channels, service
from livepulse.modules.chat import models as cm
from livepulse.shared import auth as clerk
from livepulse.shared.config import settings

INGEST = {'Authorization': 'Bearer ingest-secret'}
READ = {'Authorization': 'Bearer read-secret'}
API, AUTO, CHAT = '/api/social-live', '/api/automation', '/api/chat'
ROLES = {'root': None, 'jefa': 'jefe_marketing', 'sup': 'supervisor', 'ana': 'agente_ventas'}
PATIENT = '+51987654321'


async def test_widget_settings_persist_and_enforce_admin_permission(world):
    client, _ = world
    defaults = (await client.get(f'{AUTO}/studio/widget', headers=person('sup'))).json()
    assert defaults['position'] == 'right'
    config = {**defaults, 'title': 'Habla con Medical', 'whatsapp': '+51987654321',
              'instagram_enabled': True, 'instagram': 'medical.clinica'}
    assert (await client.put(f'{AUTO}/studio/widget', headers=person('sup'), json=config)).status_code == 403
    assert (await client.put(f'{AUTO}/studio/widget', headers=person('root'), json=config)).status_code == 200
    assert (await client.get(f'{AUTO}/studio/widget', headers=person('jefa'))).json() == config
    for bad in ({'color': 'red;position:fixed'}, {'whatsapp': 'javascript:alert(1)'},
                {'instagram': 'https://evil.example'}, {'position': 'middle'}):
        response = await client.put(f'{AUTO}/studio/widget', headers=person('root'), json={**config, **bad})
        assert response.status_code == 422


async def test_message_presets_create_reusable_drafts_and_only_test_in_simulator(world):
    client, factory = world
    keys = ['welcome', 'lead', 'appointment', 'followup']
    items = [{'key': key, 'text': f'Mensaje {key}', 'enabled': True, 'delay_minutes': 5} for key in keys]
    assert (await client.put(f'{AUTO}/studio/messages', headers=person('jefa'), json={'items': items})).status_code == 403
    response = await client.put(f'{AUTO}/studio/messages', headers=person('root'), json={'items': items})
    assert response.status_code == 200, response.text
    first = response.json()['items']
    items[0]['text'] = 'Bienvenida actualizada'
    saved = (await client.put(f'{AUTO}/studio/messages', headers=person('root'), json={'items': items})).json()['items']
    assert [p['flow_id'] for p in first] == [p['flow_id'] for p in saved]
    assert (await client.get(f'{AUTO}/studio/messages', headers=person('sup'))).json()['items'] == saved
    async with factory() as session:
        for p in saved:
            flow = await session.get(am.Flow, p['flow_id'])
            assert flow.channel_id == 'simulador' and not flow.enabled
            assert graph.validate(flow.graph) == []
            if p['key'] == 'appointment':
                assert flow.graph['nodes'][0]['type'] == 'trigger.manual'
    result = await client.post(f"{AUTO}/flows/{saved[0]['flow_id']}/test", headers=person('root'),
                               json={'text': 'Hola'})
    assert result.status_code == 200, result.text
    assert any(m['body'] == 'Bienvenida actualizada' for m in result.json()['messages'])


async def test_message_presets_reject_missing_duplicate_or_blank_stages(world):
    client, _ = world
    for items in ([], [{'key': 'welcome', 'text': 'Hola'}] * 4,
                  [{'key': key, 'text': ' '} for key in ['welcome', 'lead', 'appointment', 'followup']]):
        assert (await client.put(f'{AUTO}/studio/messages', headers=person('root'), json={'items': items})).status_code == 422


def person(name):
    return {'Authorization': f'Bearer user:{name}'}


@pytest.fixture
def people(monkeypatch):
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)
    monkeypatch.setattr(settings, 'admin_user_ids', ['root'])    # root is the admin

    def fake_verify(token):
        if not token.startswith('user:'):
            raise HTTPException(401, 'Sesión inválida o vencida.')
        uid = token.removeprefix('user:')
        return {'id': uid, 'role': ROLES.get(uid)}

    monkeypatch.setattr(clerk, 'verify_token', fake_verify)
    monkeypatch.setattr(settings, 'app_encryption_key', Fernet.generate_key().decode())


@pytest.fixture
async def world(env, people):
    client, factory = env
    async with factory() as s, s.begin():
        s.add_all([UserRole(user_id=u, role=r or 'supervisor', display_name=u.title())
                   for u, r in ROLES.items()])
    return client, factory


def node(node_id, kind, **config):
    return {'id': node_id, 'type': kind, 'config': config}


def line(*nodes):
    """A straight flow: the nodes in order."""
    return {'nodes': list(nodes), 'edges': [{'from': a['id'], 'to': b['id']}
                                            for a, b in zip(nodes, nodes[1:], strict=False)]}


async def make_flow(client, graph_, channel='simulador', enable=True, name='Flujo'):
    r = await client.post(f'{AUTO}/flows', headers=person('root'),
                          json={'name': name, 'channel_id': channel, 'graph': graph_})
    assert r.status_code == 201, r.text
    flow_id = r.json()['id']
    if enable:
        r = await client.post(f'{AUTO}/flows/{flow_id}/enable', headers=person('root'))
        assert r.status_code == 200, r.text
    return flow_id


async def patient_says(client, text, phone=PATIENT):
    r = await client.post(f'{CHAT}/simulator/inbound', headers=person('root'),
                          json={'phone': phone, 'text': text, 'name': 'Camila'})
    assert r.status_code == 200, r.text
    return r.json()


def bot_texts(result):
    return [m['body'] for m in result['messages'] if m['author_kind'] == 'bot'
            and m['status'] == 'sent']


@pytest.fixture(autouse=True)
async def overview(world):
    client, _ = world
    await client.get(f'{AUTO}/overview', headers=person('root'))   # creates the simulator channel


# ---- diagram validation ----------------------------------------------------------------------

def test_valid_and_invalid_diagrams():
    ok = line(node('t', 'trigger.message', match='any'), node('s', 'action.send_text', text='Hola'),
              node('e', 'action.end'))
    assert graph.validate(ok) == []

    cases = {
        'sin disparador': line(node('s', 'action.send_text', text='Hola')),
        'dos disparadores': {'nodes': [node('a', 'trigger.manual'), node('b', 'trigger.manual')],
                             'edges': []},
        'mensaje vacío': line(node('t', 'trigger.manual'), node('s', 'action.send_text', text=' ')),
        'webhook sin https': line(node('t', 'trigger.manual'),
                                  node('w', 'action.webhook', url='http://x.com')),
        'espera inválida': line(node('t', 'trigger.manual'), node('w', 'action.wait', minutes=0)),
        'tipo desconocido': line(node('t', 'trigger.manual'), node('x', 'action.explota')),
        'no alcanzable': {'nodes': [node('t', 'trigger.manual'), node('e', 'action.end')],
                          'edges': []},
        'conexión a la nada': {'nodes': [node('t', 'trigger.manual')],
                               'edges': [{'from': 't', 'to': 'zz'}]},
    }
    for label, bad in cases.items():
        assert graph.validate(bad), label
    cycle = {'nodes': [node('t', 'trigger.manual'), node('a', 'action.add_tag', tag='x'),
                       node('b', 'action.add_tag', tag='y')],
             'edges': [{'from': 't', 'to': 'a'}, {'from': 'a', 'to': 'b'},
                       {'from': 'b', 'to': 'a'}]}
    assert any('ciclo' in e for e in graph.validate(cycle))
    branch = {'nodes': [node('t', 'trigger.manual'), node('c', 'condition.tag', tag='vip'),
                        node('a', 'action.end')],
              'edges': [{'from': 't', 'to': 'c'}, {'from': 'c', 'to': 'a'}]}
    assert any('yes' in e for e in graph.validate(branch))
    assert graph.validate({'nodes': [node(f'n{i}', 'action.end') for i in range(41)]})


# ---- who can do what -------------------------------------------------------------------------

async def test_only_the_admin_changes_things_and_managers_only_look(world):
    client, _ = world
    body = {'name': 'F', 'channel_id': 'simulador',
            'graph': line(node('t', 'trigger.manual'), node('e', 'action.end'))}
    assert (await client.post(f'{AUTO}/flows', headers=person('root'), json=body)).status_code == 201
    for who in ('jefa', 'sup', 'ana'):
        assert (await client.post(f'{AUTO}/flows', headers=person(who), json=body)).status_code == 403
    for who in ('jefa', 'sup'):
        assert (await client.get(f'{AUTO}/flows', headers=person(who))).status_code == 200
        assert (await client.get(f'{AUTO}/overview', headers=person(who))).status_code == 200
        assert (await client.get(f'{AUTO}/ai/config', headers=person(who))).status_code == 200
        assert (await client.put(f'{AUTO}/ai/config', headers=person(who),
                                 json={'enabled': True})).status_code == 403
        # conversations (patients' messages) are for the admin only
        assert (await client.get(f'{CHAT}/conversations', headers=person(who))).status_code == 403
    assert (await client.get(f'{AUTO}/flows', headers=person('ana'))).status_code == 403
    assert (await client.get(f'{AUTO}/flows')).status_code == 401
    for token in (INGEST, READ):                      # service tokens never reach these tools
        assert (await client.get(f'{AUTO}/flows', headers=token)).status_code == 403


# ---- flows on the simulator --------------------------------------------------------------------

async def test_flow_answers_matching_messages_only_when_enabled(world):
    client, _ = world
    flow = await make_flow(client, line(
        node('t', 'trigger.message', match='keyword', keywords=['precio']),
        node('s', 'action.send_text', text='Hola {{nombre|paciente}}, la valoración cuesta S/ 80.'),
        node('g', 'action.add_tag', tag='pidio-precio')), enable=False)
    assert bot_texts(await patient_says(client, 'cuál es el PRECIO?')) == []     # still off
    await client.post(f'{AUTO}/flows/{flow}/enable', headers=person('root'))
    assert bot_texts(await patient_says(client, 'buenas tardes', '+51987000001')) == []
    result = await patient_says(client, 'Me das el precio por favor', '+51987000002')
    assert bot_texts(result) == ['Hola Camila, la valoración cuesta S/ 80.']
    assert result['conversation']['tags'] == ['pidio-precio']
    runs = (await client.get(f'{AUTO}/flows/{flow}/runs', headers=person('root'))).json()['items']
    assert runs and runs[0]['status'] == 'done'
    steps = (await client.get(f'{AUTO}/runs/{runs[0]["id"]}', headers=person('jefa'))).json()
    assert [s['type'] for s in steps['steps']] == ['trigger.message', 'action.send_text',
                                                   'action.add_tag']


async def test_branches_and_the_test_button(world):
    client, _ = world
    g = {'nodes': [node('t', 'trigger.message', match='any'),
                   node('c', 'condition.keyword', keywords=['cita', 'agendar']),
                   node('y', 'action.send_text', text='Te ayudo a agendar.'),
                   node('n', 'action.send_text', text='Cuéntame en qué te ayudo.')],
         'edges': [{'from': 't', 'to': 'c'}, {'from': 'c', 'to': 'y', 'when': 'yes'},
                   {'from': 'c', 'to': 'n', 'when': 'no'}]}
    flow = await make_flow(client, g, enable=False)
    yes = (await client.post(f'{AUTO}/flows/{flow}/test', headers=person('root'),
                             json={'text': 'quiero agendar'})).json()
    no = (await client.post(f'{AUTO}/flows/{flow}/test', headers=person('root'),
                            json={'text': 'hola'})).json()
    assert [m['body'] for m in yes['messages']] == ['Te ayudo a agendar.']
    assert [m['body'] for m in no['messages']] == ['Cuéntame en qué te ayudo.']
    assert yes['status'] == 'done' and yes['test'] is True


async def test_wait_node_resumes_when_due_and_stops_if_a_person_takes_over(world):
    client, factory = world
    await make_flow(client, line(
        node('t', 'trigger.message', match='any'), node('w', 'action.wait', minutes=5),
        node('s', 'action.send_text', text='¿Sigues interesada?')))
    first = await patient_says(client, 'hola')
    assert bot_texts(first) == []
    async with factory() as s:
        run = (await s.scalars(select(am.FlowRun))).one()
        assert run.status == 'waiting'
    assert await engine.tick(factory, engine.utcnow() + timedelta(minutes=1)) == 0   # too soon
    assert await engine.tick(factory, engine.utcnow() + timedelta(minutes=6)) == 1
    convs = (await client.get(f'{CHAT}/conversations', headers=person('root'))).json()['items']
    msgs = (await client.get(f'{CHAT}/conversations/{convs[0]["id"]}/messages',
                             headers=person('root'))).json()['messages']
    assert [m['body'] for m in msgs if m['author_kind'] == 'bot'] == ['¿Sigues interesada?']

    # a second conversation: a person answers while the bot is waiting -> the bot stays out
    await patient_says(client, 'hola', '+51987000009')
    convs = (await client.get(f'{CHAT}/conversations', headers=person('root'))).json()['items']
    other = [c for c in convs if c['phone'] == '+51987000009'][0]
    sent = await client.post(f'{CHAT}/conversations/{other["id"]}/messages',
                             headers=person('root'), json={'text': 'Hola, soy una persona.'})
    assert sent.status_code == 200
    await engine.tick(factory, engine.utcnow() + timedelta(minutes=10))
    msgs = (await client.get(f'{CHAT}/conversations/{other["id"]}/messages',
                             headers=person('root'))).json()['messages']
    assert [m['body'] for m in msgs if m['author_kind'] == 'bot'] == []
    async with factory() as s:
        stopped = (await s.scalars(select(am.FlowRun).where(am.FlowRun.status == 'stopped'))).all()
        assert len(stopped) == 1 and 'persona' in stopped[0].reason
    # and the next message does not wake the bot either, until an admin gives it back
    assert bot_texts(await patient_says(client, 'gracias', '+51987000009')) == []
    await client.patch(f'{CHAT}/conversations/{other["id"]}', headers=person('root'),
                       json={'bot_active': True})
    assert bot_texts(await patient_says(client, 'otra duda', '+51987000009')) == []   # wait node


async def test_opt_out_words_stop_the_bot_for_that_person(world):
    client, factory = world
    await make_flow(client, line(node('t', 'trigger.message', match='any'),
                                 node('s', 'action.send_text', text='Hola')))
    assert bot_texts(await patient_says(client, 'hola')) == ['Hola']
    assert bot_texts(await patient_says(client, 'BAJA', '+51987000003')) == []
    async with factory() as s:
        assert await s.get(cm.OptOut, '+51987000003') is not None
    # a message that is not the opt-out word still gets its answer for others
    assert bot_texts(await patient_says(client, 'hola', '+51987000004')) == ['Hola']


# ---- the risky channel -----------------------------------------------------------------------

class FakeMirror:
    def __init__(self):
        self.sent = []

    async def send(self, phone, text):
        self.sent.append((phone, text))
        return channels.SendResult(external_id=f'fake-{len(self.sent)}')


@pytest.fixture
def fake_mirror(monkeypatch):
    fake = FakeMirror()
    monkeypatch.setitem(channels._ADAPTERS, 'whatsapp_mirror', fake)
    return fake


async def inbound_on(factory, channel_id, text, phone=PATIENT):
    async with factory() as s, s.begin():
        return await service.receive_message(s, channel_id, phone, text, name='Camila')


async def test_mirror_channel_blocks_bots_until_an_admin_accepts_the_risk(world, fake_mirror):
    client, factory = world
    r = await client.post(f'{AUTO}/channels', headers=person('root'),
                          json={'id': 'espejo', 'kind': 'whatsapp_mirror', 'name': 'Espejo'})
    assert r.status_code == 201
    assert r.json()['policy']['bots_enabled'] is False and r.json()['risky_automation'] is True
    flow = await make_flow(client, line(node('t', 'trigger.message', match='any'),
                                        node('s', 'action.send_text', text='Hola')),
                           channel='espejo', enable=False)
    enabled = await client.post(f'{AUTO}/flows/{flow}/enable', headers=person('root'))
    assert enabled.status_code == 200 and 'apagados' in enabled.json()['warnings'][0]

    await inbound_on(factory, 'espejo', 'hola')
    assert fake_mirror.sent == []                               # bots are off: nothing leaves
    async with factory() as s:
        blocked = (await s.scalars(select(cm.ChatMessage).where(
            cm.ChatMessage.status == 'blocked'))).all()
        assert [b.error for b in blocked] == ['bots_disabled']

    # turning bots on needs the explicit acknowledgement
    refused = await client.patch(f'{AUTO}/channels/espejo', headers=person('root'),
                                 json={'policy': {'bots_enabled': True}})
    assert refused.status_code == 422 and 'bloqueen' in refused.json()['detail']
    ok = await client.patch(f'{AUTO}/channels/espejo', headers=person('root'),
                            json={'policy': {'bots_enabled': True}, 'acknowledge_risk': True})
    assert ok.status_code == 200 and ok.json()['policy']['test_only'] is True

    # still only for the test list
    await inbound_on(factory, 'espejo', 'hola otra vez', '+51987000005')
    assert fake_mirror.sent == []
    await client.patch(f'{AUTO}/channels/espejo', headers=person('root'),
                       json={'policy': {'test_numbers': ['+51987000006'], 'min_delay_s': 0}})
    await inbound_on(factory, 'espejo', 'hola', '+51987000006')
    assert fake_mirror.sent == [('+51987000006', 'Hola')]

    # and inside the hourly cap
    await client.patch(f'{AUTO}/channels/espejo', headers=person('root'),
                       json={'policy': {'bot_max_per_hour': 1}})
    await inbound_on(factory, 'espejo', 'otra', '+51987000006')
    async with factory() as s:
        waiting = (await s.scalars(select(am.FlowRun).where(am.FlowRun.status == 'waiting'))).all()
    assert len(fake_mirror.sent) == 1 and len(waiting) == 1       # retried later, not dropped

    log = (await client.get(f'{AUTO}/audit', headers=person('root'))).json()['items']
    policies = [a for a in log if a['action'] == 'policy']
    assert policies and policies[0]['detail']['changed'] == {'bot_max_per_hour': 1}   # newest first
    assert any(a['detail'].get('acknowledged_risk') for a in policies)


async def test_unlinked_mirror_does_not_pretend_to_send(world):
    client, factory = world
    await client.post(f'{AUTO}/channels', headers=person('root'),
                      json={'id': 'espejo', 'kind': 'whatsapp_mirror', 'name': 'Espejo'})
    await client.patch(f'{AUTO}/channels/espejo', headers=person('root'),
                       json={'policy': {'bots_enabled': True, 'test_only': False,
                                        'min_delay_s': 0}, 'acknowledge_risk': True})
    await make_flow(client, line(node('t', 'trigger.message', match='any'),
                                 node('s', 'action.send_text', text='Hola')), channel='espejo')
    await inbound_on(factory, 'espejo', 'hola')
    async with factory() as s:
        assert (await s.scalars(select(cm.ChatMessage).where(
            cm.ChatMessage.direction == 'out'))).all() == []
        run = (await s.scalars(select(am.FlowRun))).one()
    assert run.status == 'waiting'          # the gateway is not linked yet: it will retry


# ---- AI agent --------------------------------------------------------------------------------

async def add_knowledge(client):
    r = await client.post(f'{AUTO}/ai/knowledge', headers=person('root'), json={
        'title': 'Horarios', 'body': 'Atendemos de lunes a sábado de 9 a 1 en la sede de Miraflores.\n\n'
                                      'La valoración con el cirujano cuesta S/ 80.'})
    assert r.status_code == 201


async def playground(client, text):
    r = await client.post(f'{AUTO}/ai/playground', headers=person('root'),
                          json={'messages': [{'role': 'user', 'content': text}]})
    assert r.status_code == 200, r.text
    return r.json()


async def test_ai_agent_answers_from_knowledge_and_hands_off_when_it_should(world):
    client, _ = world
    first = await playground(client, 'qué horario atienden?')
    assert first['handoff'] is True and first['reason'] == 'sin_conocimiento'   # nothing to say yet
    await add_knowledge(client)
    answer = await playground(client, 'a qué horario atienden en miraflores')
    assert answer['handoff'] is False and 'lunes a sábado' in answer['text']
    pain = await playground(client, 'tengo mucho dolor después de la operación')
    assert pain['handoff'] is True and pain['reason'] == 'palabra_de_traspaso'
    unknown = await playground(client, 'aceptan criptomonedas')
    assert unknown['handoff'] is True and unknown['reason'] == 'sin_conocimiento'
    bad = await client.post(f'{AUTO}/ai/playground', headers=person('root'),
                            json={'messages': [{'role': 'assistant', 'content': 'hola'}]})
    assert bad.status_code == 422


async def test_ai_reply_node_answers_then_hands_the_chat_to_a_person(world):
    client, factory = world
    await add_knowledge(client)
    await client.put(f'{AUTO}/ai/config', headers=person('root'), json={'enabled': True})
    await make_flow(client, line(node('t', 'trigger.message', match='any'),
                                 node('a', 'action.ai_reply')))
    answered = await patient_says(client, 'cuánto cuesta la valoración con el cirujano')
    assert 'S/ 80' in bot_texts(answered)[0]
    handed = await patient_says(client, 'me duele mucho, es una emergencia')
    assert 'persona' in bot_texts(handed)[-1].lower()
    assert handed['conversation']['bot_active'] is False
    # from now on the bot stays out of this chat
    assert len(bot_texts(await patient_says(client, 'gracias'))) == len(bot_texts(handed))
    usage = (await client.get(f'{AUTO}/ai/usage', headers=person('jefa'))).json()['items']
    assert usage[0]['messages'] == 1                                  # only the real AI call


async def test_provider_key_is_encrypted_never_returned_and_the_safety_rules_are_always_sent(
        world, monkeypatch):
    client, factory = world
    await add_knowledge(client)
    refused = await client.put(f'{AUTO}/ai/config', headers=person('root'),
                               json={'provider': 'anthropic', 'enabled': True})
    assert refused.status_code == 422                                  # no key, no model
    calls = []

    async def fake_post(url, headers, payload):
        calls.append((url, headers, payload))
        return {'content': [{'type': 'text', 'text': 'Le consulto al equipo. [[HANDOFF]]'}],
                'usage': {'input_tokens': 120, 'output_tokens': 15}}

    monkeypatch.setattr(ai, '_post', fake_post)
    saved = await client.put(f'{AUTO}/ai/config', headers=person('root'), json={
        'provider': 'anthropic', 'model': 'claude-haiku-5-5', 'api_key': 'sk-ant-secret-1234',
        'enabled': True, 'instructions': 'Sé amable.'})
    assert saved.status_code == 200
    body = saved.json()
    assert body['has_key'] is True and body['key_hint'] == '••••1234'
    assert 'sk-ant' not in saved.text and 'api_key_encrypted' not in saved.text
    assert 'sk-ant' not in (await client.get(f'{AUTO}/ai/config', headers=person('jefa'))).text
    async with factory() as s:
        stored = (await s.get(am.AiAgent, 1)).api_key_encrypted
    assert stored and 'sk-ant' not in stored                            # encrypted at rest

    result = await playground(client, 'a qué horario atienden en miraflores')
    url, headers, payload = calls[0]
    assert url == 'https://api.anthropic.com/v1/messages'
    assert headers['x-api-key'] == 'sk-ant-secret-1234'
    assert 'NO diagnostiques' in payload['system'] and 'Sé amable.' in payload['system']
    assert 'lunes a sábado' in payload['system']                        # the knowledge goes in
    assert result['handoff'] is True and result['text'] == 'Le consulto al equipo.'
    audit_rows = (await client.get(f'{AUTO}/audit', headers=person('root'))).json()['items']
    assert not any('sk-ant' in str(a['detail']) for a in audit_rows)


# ---- broadcasts ------------------------------------------------------------------------------

async def seed_contacts(client, count):
    await client.post(f'{API}/accounts', headers=INGEST,
                      json={'id': 'medical', 'name': 'm', 'username': 'medical.cirugias'})
    await client.post(f'{API}/lives', headers=INGEST, json={
        'live_id': 'L1', 'account_id': 'medical', 'started_at': '2026-10-01T12:00:00'})
    phones = []
    for i in range(count):
        phone = f'98{i + 1:07d}'
        await client.post(f'{API}/lives/L1/comments', headers=INGEST, json={
            'username': f'user{i}', 'text': f'quiero info {phone}',
            'timestamp': (engine.utcnow() - timedelta(minutes=500 - i)).isoformat()})
        phones.append('+51' + phone)
    return phones


async def test_broadcast_lifecycle_on_the_simulator(world):
    client, factory = world
    phones = await seed_contacts(client, 7)
    await patient_says(client, 'BAJA', phones[0])             # one person already opted out
    body = {'name': 'Prueba', 'channel_id': 'simulador',
            'body': 'Hola {{nombre|paciente}}, ¿sigues interesada en tu valoración?',
            'audience': {'statuses': ['new'], 'require_consent': False}}
    preview = await client.post(f'{AUTO}/broadcasts/preview', headers=person('root'),
                                json={'audience': body['audience']})
    assert preview.json()['count'] == 6                       # the opted-out one is not in it
    created = await client.post(f'{AUTO}/broadcasts', headers=person('root'), json=body)
    assert created.status_code == 201 and created.json()['total'] == 6
    bid = created.json()['id']

    wrong = await client.post(f'{AUTO}/broadcasts/{bid}/start', headers=person('root'),
                              json={'confirm_total': 5})
    assert wrong.status_code == 422 and '6' in wrong.json()['detail']
    started = await client.post(f'{AUTO}/broadcasts/{bid}/start', headers=person('root'),
                                json={'confirm_total': 6})
    assert started.json()['status'] == 'sending'
    assert await broadcast_sender.tick(factory) == 5          # one small batch per tick
    await client.post(f'{AUTO}/broadcasts/{bid}/pause', headers=person('root'))
    assert await broadcast_sender.tick(factory) == 0          # paused: nothing goes out
    await client.post(f'{AUTO}/broadcasts/{bid}/resume', headers=person('root'))
    assert await broadcast_sender.tick(factory) == 1
    assert await broadcast_sender.tick(factory) == 0
    detail = (await client.get(f'{AUTO}/broadcasts/{bid}', headers=person('root'))).json()
    assert detail['status'] == 'done' and detail['sent'] == 6
    assert detail['recipients_by_status'] == {'sent': 6}
    assert len(detail['recipients']) == 6
    looked = (await client.get(f'{AUTO}/broadcasts/{bid}', headers=person('jefa'))).json()
    assert 'recipients' not in looked and looked['sent'] == 6     # managers: counts, no phones
    convs = (await client.get(f'{CHAT}/conversations', headers=person('root'))).json()['items']
    assert any(c['phone'] == phones[1] for c in convs)
    assert not any(c['last'] and c['last']['broadcast_id'] and c['phone'] == phones[0]
                   for c in convs)


async def test_broadcast_on_the_mirror_pauses_itself_when_the_policy_forbids_it(world, fake_mirror):
    client, factory = world
    phones = await seed_contacts(client, 3)
    await client.post(f'{AUTO}/channels', headers=person('root'),
                      json={'id': 'espejo', 'kind': 'whatsapp_mirror', 'name': 'Espejo'})
    created = await client.post(f'{AUTO}/broadcasts', headers=person('root'), json={
        'name': 'Muestra', 'channel_id': 'espejo', 'body': 'Hola',
        'audience': {'phones': phones, 'require_consent': False}})
    bid = created.json()['id']
    await client.post(f'{AUTO}/broadcasts/{bid}/start', headers=person('root'),
                      json={'confirm_total': 3})
    assert await broadcast_sender.tick(factory) == 0
    detail = (await client.get(f'{AUTO}/broadcasts/{bid}', headers=person('root'))).json()
    assert detail['status'] == 'paused' and 'apagadas' in detail['pause_reason']
    assert fake_mirror.sent == []

    # a test message needs the number to be on the test list
    blocked = await client.post(f'{AUTO}/broadcasts/{bid}/test', headers=person('root'),
                                json={'phone': phones[0]})
    assert blocked.status_code == 409
    await client.patch(f'{AUTO}/channels/espejo', headers=person('root'), json={
        'policy': {'broadcasts_enabled': True, 'test_numbers': [phones[0]], 'min_delay_s': 0},
        'acknowledge_risk': True})
    sent = await client.post(f'{AUTO}/broadcasts/{bid}/test', headers=person('root'),
                             json={'phone': phones[0]})
    assert sent.status_code == 200 and fake_mirror.sent == [(phones[0], 'Hola')]
    # the other two recipients are not on the list: the broadcast pauses again, nothing leaks
    await client.post(f'{AUTO}/broadcasts/{bid}/resume', headers=person('root'))
    await broadcast_sender.tick(factory)
    assert [p for p, _ in fake_mirror.sent] == [phones[0], phones[0]]
    detail = (await client.get(f'{AUTO}/broadcasts/{bid}', headers=person('root'))).json()
    assert detail['status'] == 'paused'
