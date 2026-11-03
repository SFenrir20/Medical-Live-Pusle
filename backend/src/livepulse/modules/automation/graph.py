"""The diagram of a flow and its validation.

A flow is JSON: {"nodes": [{"id", "type", "config"}], "edges": [{"from", "to", "when"}]}.
The visual canvas and the simple step form are only two editors of this same JSON, and the
engine (engine.py) is the only thing that executes it. Branching nodes (conditions) have up to
two outgoing edges, `when: "yes"` and `when: "no"`; every other node has at most one."""
import re
from urllib.parse import urlsplit

ID = re.compile(r'^[a-z0-9_-]{1,20}$')
MAX_NODES = 40
STATUSES = ('new', 'contacted', 'qualified', 'discarded')

TRIGGERS = ('trigger.message', 'trigger.manual')
CONDITIONS = ('condition.keyword', 'condition.tag', 'condition.status',
              'condition.business_hours')
ACTIONS = ('action.send_text', 'action.wait', 'action.add_tag', 'action.set_status',
           'action.assign', 'action.handoff', 'action.ai_reply', 'action.webhook', 'action.end')
NODE_TYPES = TRIGGERS + CONDITIONS + ACTIONS

# Shown in the editor: label and help of each node type.
CATALOG = {
    'trigger.message': ('Mensaje entrante', 'Empieza cuando la persona escribe (cualquier '
                                            'mensaje o con una palabra clave).'),
    'trigger.manual': ('Prueba manual', 'Solo se ejecuta desde el botón de prueba.'),
    'condition.keyword': ('¿Dijo la palabra?', 'Sí/No según el último mensaje de la persona.'),
    'condition.tag': ('¿Tiene la etiqueta?', 'Sí/No según las etiquetas de la conversación.'),
    'condition.status': ('¿Estado del contacto?', 'Sí/No según el estado del contacto.'),
    'condition.business_hours': ('¿Dentro del horario?', 'Sí/No según día y hora de Lima.'),
    'action.send_text': ('Enviar mensaje', 'Texto con variables {{nombre}} y {{telefono}}.'),
    'action.wait': ('Esperar', 'Pausa el flujo unos minutos.'),
    'action.add_tag': ('Poner etiqueta', 'Agrega una etiqueta a la conversación.'),
    'action.set_status': ('Cambiar estado', 'Cambia el estado del contacto.'),
    'action.assign': ('Asignar a un agente', 'Lo entrega al siguiente agente conectado.'),
    'action.handoff': ('Pasar a una persona', 'Detiene el bot y lo asigna a un agente.'),
    'action.ai_reply': ('Responde la IA', 'El agente de IA contesta con su conocimiento.'),
    'action.webhook': ('Llamar a un webhook', 'Avisa a otro sistema (https).'),
    'action.end': ('Terminar', 'Fin del flujo.'),
}


def _config_errors(node: dict) -> list[str]:
    kind, config, tag = node['type'], node.get('config') or {}, node['id']
    errors = []

    def need(condition: bool, message: str):
        if not condition:
            errors.append(f'«{tag}»: {message}')

    if kind == 'trigger.message':
        match = config.get('match', 'any')
        need(match in ('any', 'keyword'), 'match debe ser any o keyword')
        if match == 'keyword':
            need(_words(config.get('keywords')), 'indica al menos una palabra clave')
    elif kind == 'condition.keyword':
        need(_words(config.get('keywords')), 'indica al menos una palabra clave')
    elif kind in ('condition.tag', 'action.add_tag'):
        need(isinstance(config.get('tag'), str) and 0 < len(config['tag'].strip()) <= 30,
             'la etiqueta debe tener entre 1 y 30 caracteres')
    elif kind in ('condition.status',):
        value = config.get('statuses')
        need(isinstance(value, list) and value and all(v in STATUSES for v in value),
             'indica estados válidos')
    elif kind == 'action.set_status':
        need(config.get('status') in STATUSES, 'estado inválido')
    elif kind == 'condition.business_hours':
        need(_hhmm(config.get('start')) and _hhmm(config.get('end')),
             'horario con formato HH:MM')
        days = config.get('days', [0, 1, 2, 3, 4])
        need(isinstance(days, list) and all(isinstance(d, int) and 0 <= d <= 6 for d in days),
             'días entre 0 (lunes) y 6 (domingo)')
    elif kind in ('action.send_text', 'action.handoff'):
        text = config.get('text', '')
        if kind == 'action.send_text':
            need(isinstance(text, str) and 0 < len(text.strip()) <= 1000,
                 'el mensaje debe tener entre 1 y 1000 caracteres')
        else:
            need(isinstance(text, str) and len(text) <= 1000, 'el mensaje es demasiado largo')
    elif kind == 'action.wait':
        minutes = config.get('minutes')
        need(isinstance(minutes, int) and 1 <= minutes <= 10080, 'minutos entre 1 y 10080')
    elif kind == 'action.webhook':
        url = urlsplit(str(config.get('url', '')))
        need(url.scheme == 'https' and bool(url.hostname), 'la URL debe ser https')
    return errors


def _words(value) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(v, str) and 0 < len(v.strip()) <= 40 for v in value)


def _hhmm(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', value) is not None


def validate(graph) -> list[str]:
    """Every problem found, in Spanish and by node, so the editor can show them all."""
    if not isinstance(graph, dict):
        return ['El flujo debe ser un objeto con nodos y conexiones.']
    nodes, edges = graph.get('nodes'), graph.get('edges', [])
    if not isinstance(nodes, list) or not nodes:
        return ['El flujo no tiene nodos.']
    if len(nodes) > MAX_NODES:
        return [f'Máximo {MAX_NODES} nodos por flujo.']
    errors, by_id = [], {}
    for node in nodes:
        if not isinstance(node, dict) or not ID.match(str(node.get('id', ''))):
            return ['Cada nodo necesita un id de 1 a 20 letras minúsculas, números, - o _.']
        if node['id'] in by_id:
            return [f'Id repetido: «{node["id"]}».']
        if node.get('type') not in NODE_TYPES:
            errors.append(f'«{node["id"]}»: tipo de nodo desconocido.')
            continue
        by_id[node['id']] = node
        errors += _config_errors(node)
    triggers = [n for n in by_id.values() if n['type'] in TRIGGERS]
    if len(triggers) != 1:
        errors.append('Debe haber exactamente un disparador.')
    out: dict[str, list[dict]] = {}
    if not isinstance(edges, list):
        return errors + ['Las conexiones deben ser una lista.']
    for edge in edges:
        if not isinstance(edge, dict) or edge.get('from') not in by_id or edge.get('to') not in by_id:
            errors.append('Hay una conexión hacia un nodo que no existe.')
            continue
        out.setdefault(edge['from'], []).append(edge)
        if by_id[edge['to']]['type'] in TRIGGERS:
            errors.append('Nada puede conectarse hacia el disparador.')
    for node_id, node in by_id.items():
        outgoing = out.get(node_id, [])
        if node['type'] in CONDITIONS:
            whens = [e.get('when') for e in outgoing]
            if any(w not in ('yes', 'no') for w in whens) or len(set(whens)) != len(whens):
                errors.append(f'«{node_id}»: las salidas deben ser una «yes» y una «no».')
        elif len(outgoing) > 1 or any(e.get('when') for e in outgoing):
            errors.append(f'«{node_id}»: solo puede tener una salida.')
        if node['type'] == 'action.end' and outgoing:
            errors.append(f'«{node_id}»: «Terminar» no tiene salidas.')
    if len(triggers) == 1 and not errors:
        seen, stack = set(), [triggers[0]['id']]
        while stack:  # reachability and cycles (a loop could run forever)
            current = stack.pop()
            seen.add(current)
            stack += [e['to'] for e in out.get(current, []) if e['to'] not in seen]
        if seen != set(by_id):
            errors.append('Hay nodos que no se alcanzan desde el disparador.')
        if _has_cycle(by_id, out):
            errors.append('El flujo tiene un ciclo: podría repetirse sin fin.')
    return errors


def _has_cycle(by_id, out) -> bool:
    state: dict[str, int] = {}

    def visit(node_id: str) -> bool:
        state[node_id] = 1
        for edge in out.get(node_id, []):
            nxt = edge['to']
            if state.get(nxt) == 1 or (nxt not in state and visit(nxt)):
                return True
        state[node_id] = 2
        return False

    return any(node_id not in state and visit(node_id) for node_id in by_id)


def trigger_of(graph: dict) -> dict:
    return next(n for n in graph['nodes'] if n['type'] in TRIGGERS)


def next_nodes(graph: dict, node_id: str, branch: str | None = None) -> list[str]:
    result = []
    for edge in graph.get('edges', []):
        if edge['from'] == node_id and (branch is None or edge.get('when') in (None, branch)):
            result.append(edge['to'])
    return result
