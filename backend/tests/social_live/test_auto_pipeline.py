"""The automatic funnel: a confirmed appointment moves the patient to the branch funnel, tags it and
hands it to the advisor whose shift covers the hour; each branch sees only its own patients."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from livepulse.modules.analytics.models import UserRole
from livepulse.modules.chat.models import ChatConversation
from livepulse.modules.crm import autopipeline  # noqa: F401  (registers the rule)
from livepulse.modules.crm import models as cm
from livepulse.modules.social_live.models import ContactAudit, PhoneRegistry
from livepulse.modules.whatsapp import service as wa
from livepulse.shared import auth as clerk
from livepulse.shared.config import settings

INGEST = {'Authorization': 'Bearer ingest-secret'}
API, WA, CRM = '/api/social-live', '/api/whatsapp', '/api/crm'
ROLES = {'ana': 'agente_ventas', 'ase1': 'asesor', 'ase2': 'asesor', 'ase3': 'asesor',
         'sup': 'supervisor', 'jefa': 'jefe_marketing', 'boss': None}
NOW = datetime.now(timezone.utc).replace(microsecond=0)
LIVE_PHONE = '+51987654321'


def auth(user):
    return {'Authorization': f'Bearer {user}'}


@pytest.fixture
def people(monkeypatch):
    monkeypatch.setattr(clerk, 'clerk_configured', lambda: True)
    monkeypatch.setattr(settings, 'admin_user_ids', ['boss'])

    def verify(token):
        if token not in ROLES:
            raise HTTPException(401)
        return {'id': token, 'role': ROLES[token]}

    monkeypatch.setattr(clerk, 'verify_token', verify)


@pytest.fixture
async def world(env, people):
    client, factory = env
    async with factory() as s, s.begin():
        s.add_all([UserRole(user_id=u, role=r or 'supervisor', display_name=u.title())
                   for u, r in ROLES.items()])
    await client.post(f'{API}/accounts', headers=INGEST,
                      json={'id': 'medical', 'name': 'm', 'username': 'medical.cirugias'})
    await client.post(f'{API}/lives', headers=INGEST, json={
        'live_id': 'L1', 'account_id': 'medical',
        'started_at': (NOW - timedelta(hours=2)).isoformat()})
    await client.post(f'{API}/lives/L1/comments', headers=INGEST, json={
        'username': 'camila.rr', 'text': 'me interesa el precio 987654321',
        'timestamp': (NOW - timedelta(minutes=30)).isoformat()})
    sites = {s['key']: s for s in (await client.get(f'{CRM}/sites', headers=auth('ana'))).json()['items']}
    for user, site, start, end in (('ase1', 'sjm', '09:00', '17:00'), ('ase2', 'sjm', '11:00', '20:00'),
                                   ('ase3', 'san_isidro', '09:00', '17:00')):
        r = await client.put(f'{CRM}/sites/staff/{user}', headers=auth('boss'), json={
            'site_id': sites[site]['id'], 'shift_start': start, 'shift_end': end})
        assert r.status_code == 200, r.text
    return client, factory


async def open_chat(client, phone, user='ana'):
    r = await client.post(f'{WA}/conversations', headers=auth(user), json={'phone': phone})
    assert r.status_code == 200, r.text
    conversation = r.json()['id']
    assert (await client.post(f'{WA}/conversations/{conversation}/claim', headers=auth(user))).status_code == 200
    return conversation


def confirmation(hour='3pm a 4pm', site='SJM', day='1-8'):
    return (f'Muy bien, le envío los datos de su cita:\n🫶🏽Paciente: Camila Sánchez\n🗓️Fecha: {day}\n'
            f'🕐Hora: {hour}\n📌Sede: {site}\n📌Dirección: Av. Miguel Iglesias 625')


async def send_from_phone(factory, phone, text, external_id=None):
    """The centre's message really left (it is seen as sent from the device)."""
    async with factory() as s, s.begin():
        await wa.ingest(s, {'id': str(uuid4()), 'type': 'message', 'phone': phone,
                            'external_id': external_id or str(uuid4()), 'from_me': True,
                            'at': (NOW - timedelta(minutes=2)).isoformat(), 'body': text})


async def detail(client, conversation, user='sup'):
    r = await client.get(f'{CRM}/conversations/{conversation}', headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


async def book(client, factory, phone, **kwargs):
    conversation = await open_chat(client, phone)
    await send_from_phone(factory, phone, confirmation(**kwargs))
    return conversation


async def test_a_booking_moves_tags_and_hands_over_the_patient(world):
    client, factory = world
    conversation = await book(client, factory, '+51900000001')
    d = await detail(client, conversation)
    assert d['stage'] == 'qualified' and d['site'] == 'SJM'
    assert {'Cita agendada', 'SJM'} <= set(d['tags']) and 'Del LIVE' not in d['tags']
    assert d['appointment_label'] == '1-8 · 3pm a 4pm' and d['appointment_at'] is not None
    assert d['advisor_id'] in ('ase1', 'ase2')                    # both cover 3pm
    log = (await client.get(f'{CRM}/automation/log', headers=auth('sup'),
                            params={'conversation_id': conversation})).json()
    assert log['can_undo'] is True and 'SJM' in log['items'][0]['summary']
    assert 'asignada a' in log['items'][0]['summary']


async def test_the_advisor_is_chosen_by_the_shift_that_covers_the_hour(world):
    client, factory = world
    morning = await book(client, factory, '+51900000001', hour='9:30am')     # only ase1 (09-17)
    evening = await book(client, factory, '+51900000002', hour='6pm a 7pm')  # only ase2 (11-20)
    night = await book(client, factory, '+51900000003', hour='9pm')          # nobody
    assert (await detail(client, morning))['advisor_id'] == 'ase1'
    assert (await detail(client, evening))['advisor_id'] == 'ase2'
    pool = await detail(client, night)
    assert pool['advisor_id'] is None and pool['site'] == 'SJM'
    log = (await client.get(f'{CRM}/automation/log', headers=auth('sup'),
                            params={'conversation_id': night})).json()
    assert 'queda libre en la sede' in log['items'][0]['summary']


async def test_where_shifts_overlap_the_load_is_shared_and_the_connected_go_first(world):
    client, factory = world
    first = await book(client, factory, '+51900000001', hour='3pm')
    second = await book(client, factory, '+51900000002', hour='3pm')
    third = await book(client, factory, '+51900000003', hour='3pm')
    owners = [(await detail(client, c))['advisor_id'] for c in (first, second, third)]
    assert owners[0] != owners[1]                       # the second one goes to the other advisor
    assert set(owners) == {'ase1', 'ase2'}
    # ase2 connects: from now on the overlap goes to who is connected
    beat = await client.post('/api/presence/heartbeat', headers=auth('ase2'),
                             json={'visible': True, 'status': 'available'})
    assert beat.status_code == 200, beat.text
    fourth = await book(client, factory, '+51900000004', hour='3pm')
    assert (await detail(client, fourth))['advisor_id'] == 'ase2'


async def test_each_branch_sees_only_its_own_patients_and_funnel(world):
    client, factory = world
    mine = await book(client, factory, '+51900000001', hour='9:30am')        # ase1, SJM
    pool = await book(client, factory, '+51900000003', hour='9pm')           # SJM pool
    other = await book(client, factory, '+51900000005', hour='10am', site='San Isidro')
    assert (await detail(client, other))['advisor_id'] == 'ase3'

    # the centre's agent no longer sees them (the work moved to the advisors)
    assert (await client.get(f'{CRM}/conversations/{mine}', headers=auth('ana'))).status_code == 403
    assert (await client.get(f'{CRM}/conversations/{pool}', headers=auth('ana'))).status_code == 403
    listed = (await client.get(f'{CRM}/conversations', headers=auth('ana'))).json()['items']
    assert listed == []
    # the same branch sees the colleague's patient and the pool, the other branch sees neither
    assert (await client.get(f'{CRM}/conversations/{mine}', headers=auth('ase2'))).status_code == 200
    assert (await client.get(f'{CRM}/conversations/{pool}', headers=auth('ase2'))).status_code == 200
    assert (await client.get(f'{CRM}/conversations/{mine}', headers=auth('ase3'))).status_code == 403
    assert (await client.get(f'{CRM}/conversations/{pool}', headers=auth('ase3'))).status_code == 403
    assert (await client.get(f'{CRM}/conversations/{other}', headers=auth('ase1'))).status_code == 403
    ids = {i['id'] for i in (await client.get(f'{CRM}/conversations', headers=auth('ase1'))).json()['items']}
    assert ids == {mine, pool}
    # seeing is not writing: ase2 cannot answer ase1's patient, but can take the pool one
    send = await client.post(f'{WA}/conversations/{mine}/messages', headers=auth('ase2'),
                             json={'request_id': str(uuid4()), 'text': 'hola'})
    assert send.status_code == 409
    assert (await client.post(f'{WA}/conversations/{pool}/claim', headers=auth('ase2'))).status_code == 200
    # managers see everything
    assert (await client.get(f'{CRM}/conversations/{other}', headers=auth('jefa'))).status_code == 200

    async def names(user):
        r = await client.get(f'{CRM}/pipelines', headers=auth(user))
        return {p['name'] for p in r.json()['items']}

    assert await names('ana') == {'Contactos'}
    assert await names('ase1') == {'Contactos', 'Asesores · SJM'}
    assert await names('ase3') == {'Contactos', 'Asesores · San Isidro'}
    assert {'Asesores · SJM', 'Asesores · San Isidro', 'Asesores · Los Olivos',
            'Asesores · Ate'} <= await names('sup')
    sjm = next(p for p in (await client.get(f'{CRM}/pipelines', headers=auth('ase1'))).json()['items']
               if p['name'] == 'Asesores · SJM')
    assert (await client.get(f'{CRM}/pipelines/{sjm["id"]}/board', headers=auth('ase3'))).status_code == 404
    board = (await client.get(f'{CRM}/pipelines/{sjm["id"]}/board', headers=auth('ase1'))).json()
    assert [c['name'] for c in board['stages']] == ['Cita agendada', 'Asistió', 'Cotizado', 'Separado',
                                                    'Operado']
    assert board['stages'][0]['count'] == 2 and board['total'] == 2    # the two SJM patients


async def test_a_message_seen_twice_moves_nobody_twice_and_a_new_date_keeps_the_advisor(world):
    client, factory = world
    phone = '+51900000001'
    conversation = await open_chat(client, phone)
    same_id = str(uuid4())
    await send_from_phone(factory, phone, confirmation(hour='3pm'), external_id=same_id)
    owner = (await detail(client, conversation))['advisor_id']
    await send_from_phone(factory, phone, confirmation(hour='3pm'), external_id=same_id)   # re-delivered
    log = (await client.get(f'{CRM}/automation/log', headers=auth('sup'),
                            params={'conversation_id': conversation})).json()['items']
    assert len(log) == 1
    # the centre moves the appointment: same branch, the advisor stays (no second hand-over)
    await send_from_phone(factory, phone, confirmation(hour='4pm', day='2-8'))
    d = await detail(client, conversation)
    assert d['advisor_id'] == owner and d['appointment_label'] == '2-8 · 4pm'
    async with factory() as s:
        assert len((await s.scalars(select(cm.PipelineCard))).all()) == 1


async def test_an_unknown_branch_still_books_but_asks_for_review(world):
    client, factory = world
    conversation = await book(client, factory, '+51900000001', site='Cusco')
    d = await detail(client, conversation)
    assert d['stage'] == 'qualified' and d['site'] is None and 'Cita agendada' in d['tags']
    assert d['advisor_id'] == 'ana'                       # nothing was handed over
    log = (await client.get(f'{CRM}/automation/log', headers=auth('sup'),
                            params={'conversation_id': conversation})).json()
    assert 'no coincide' in log['items'][0]['summary']
    # ordinary text never triggers anything
    plain = await open_chat(client, '+51900000009')
    await send_from_phone(factory, '+51900000009', 'Nuestra sede de SJM atiende de 9 a 5')
    assert (await detail(client, plain))['stage'] == 'new'


async def test_a_supervisor_can_undo_it(world):
    client, factory = world
    conversation = await book(client, factory, '+51900000001')
    log = (await client.get(f'{CRM}/automation/log', headers=auth('sup'),
                            params={'conversation_id': conversation})).json()['items'][0]
    assert (await client.post(f'{CRM}/automation/{log["id"]}/undo', headers=auth('ase1'))).status_code == 403
    done = await client.post(f'{CRM}/automation/{log["id"]}/undo', headers=auth('sup'))
    assert done.status_code == 200, done.text
    d = await detail(client, conversation)
    assert (d['stage'], d['site'], d['advisor_id'], d['tags']) == ('new', None, 'ana', [])
    assert d['appointment_label'] is None
    async with factory() as s:
        assert (await s.scalars(select(cm.PipelineCard))).all() == []
    assert (await client.post(f'{CRM}/automation/{log["id"]}/undo', headers=auth('sup'))).status_code == 409


async def test_a_live_contact_keeps_its_audit_and_is_tagged(world):
    client, factory = world
    conversation = await open_chat(client, LIVE_PHONE)
    await send_from_phone(factory, LIVE_PHONE, confirmation(hour='10am', site='San Isidro / Lince'))
    d = await detail(client, conversation)
    assert d['advisor_id'] == 'ase3' and d['site'] == 'San Isidro' and 'Del LIVE' in d['tags']
    async with factory() as s:
        registry = await s.scalar(select(PhoneRegistry).where(PhoneRegistry.phone == LIVE_PHONE))
        assert registry.status == 'qualified' and registry.advisor_id == 'ase3'
        actions = {(a.actor, a.action) for a in (await s.scalars(select(ContactAudit))).all()}
        assert ('system:auto', 'status') in actions and ('system:auto', 'assign') in actions
        assert (await s.get(ChatConversation, conversation)).site_id is not None


async def test_branches_and_shifts_are_managed_by_the_admin(world):
    client, _ = world
    sites = (await client.get(f'{CRM}/sites', headers=auth('ana'))).json()['items']
    assert [s['name'] for s in sites] == ['San Isidro', 'Los Olivos', 'SJM', 'Ate']
    sjm = next(s for s in sites if s['key'] == 'sjm')
    body = {'site_id': sjm['id'], 'shift_start': '09:00', 'shift_end': '17:00'}
    assert (await client.put(f'{CRM}/sites/staff/ase1', headers=auth('sup'), json=body)).status_code == 403
    assert (await client.put(f'{CRM}/sites/staff/ana', headers=auth('boss'), json=body)).status_code == 404
    assert (await client.put(f'{CRM}/sites/staff/ase1', headers=auth('boss'),
                             json={**body, 'shift_end': '08:00'})).status_code == 422
    assert (await client.put(f'{CRM}/sites/staff/ase1', headers=auth('boss'),
                             json={**body, 'shift_start': '9am'})).status_code == 422
    assert (await client.put(f'{CRM}/sites/staff/ase1', headers=auth('boss'),
                             json={**body, 'site_id': 999})).status_code == 422
    staff = (await client.get(f'{CRM}/sites/staff', headers=auth('sup'))).json()['items']
    assert {s['user_id']: s['site_id'] for s in staff}['ase1'] == sjm['id']
    assert (await client.get(f'{CRM}/sites/staff', headers=auth('ana'))).status_code == 403
    # a new branch gets its own funnel; the admin can rename it and add aliases
    made = await client.post(f'{CRM}/sites', headers=auth('boss'), json={'name': 'Surco', 'aliases': ['Santiago de Surco']})
    assert made.status_code == 201 and made.json()['pipeline_id']
    assert (await client.post(f'{CRM}/sites', headers=auth('boss'), json={'name': 'Surco'})).status_code == 409
    preview = await client.post(f'{CRM}/automation/preview', headers=auth('sup'),
                                json={'text': confirmation(site='Santiago de Surco', hour='11 a 12pm')})
    assert preview.json()['is_appointment'] is True and preview.json()['site'] == 'Surco'
    assert preview.json()['hour'] == '11:00'
    assert (await client.post(f'{CRM}/automation/preview', headers=auth('ana'),
                              json={'text': 'x'})).status_code == 403
    assert (await client.post(f'{CRM}/automation/preview', headers=auth('sup'),
                              json={'text': 'hola'})).json() == {'is_appointment': False}
