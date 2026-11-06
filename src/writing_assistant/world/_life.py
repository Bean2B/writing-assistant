"""Pure bounded life rules stored inside WorldSimulation, with no I/O or models."""
from copy import deepcopy

SCHEMA = 'lotus-world-life/1'
MAX_NAMED = 128
MAX_GROUPS = 16
MAX_UNNAMED = 1000
MAX_EVENTS = 128
MAX_TIME = 1000000


def validate(state, require, fields, slug, integer, text):
    life = state['life']
    fields(life, {'schema', 'time', 'people', 'groups', 'queue', 'history'})
    require(life['schema'] == SCHEMA and integer(life['time'], MAX_TIME))
    require(type(life['people']) is dict and set(life['people']) == set(state['actors']))
    for actor, person in life['people'].items():
        fields(person, {'goal', 'schedule', 'anchor', 'relations', 'origin'})
        require(text(person['goal']) and integer(person['anchor'], life['time']))
        require(type(person['schedule']) is list and len(person['schedule']) <= 16)
        minutes = []
        for slot in person['schedule']:
            fields(slot, {'minute', 'location'})
            require(integer(slot['minute'], 1439) and slot['location'] in state['locations'])
            minutes.append(slot['minute'])
        require(minutes == sorted(set(minutes)))
        require(type(person['relations']) is dict and len(person['relations']) <= 32)
        for other, relation in person['relations'].items():
            require(other in state['actors'] and other != actor and text(relation))
        if person['origin'] is not None:
            fields(person['origin'], {'group_id', 'member_id', 'time', 'cause'})
            origin = person['origin']
            require(slug(origin['group_id']) and slug(origin['member_id'])
                    and integer(origin['time'], life['time']) and slug(origin['cause']))
    require(type(life['groups']) is dict and len(life['groups']) <= MAX_GROUPS)
    for name, group in life['groups'].items():
        fields(group, {'count', 'location', 'role', 'members'})
        require(slug(name) and integer(group['count'], MAX_UNNAMED)
                and group['location'] in state['locations'] and text(group['role'])
                and type(group['members']) is dict)
        for member, actor in group['members'].items():
            require(slug(member) and actor in state['actors'])
            origin = life['people'][actor]['origin']
            require(origin is not None and origin['group_id'] == name and origin['member_id'] == member)
    require(sum(g['count'] for g in life['groups'].values()) <= MAX_UNNAMED)
    origins = []
    for actor, person in life['people'].items():
        if person['origin'] is not None:
            origin = person['origin']
            group = life['groups'].get(origin['group_id'], {})
            require(group.get('members', {}).get(origin['member_id']) == actor)
            origins.append((origin['group_id'], origin['member_id']))
    require(len(origins) == len(set(origins)))
    require(type(life['queue']) is list and type(life['history']) is list
            and len(life['queue']) <= MAX_EVENTS)
    ids = []
    for event in life['queue']:
        fields(event, {'id', 'at', 'cause', 'participants', 'effect'})
        require(slug(event['id']) and integer(event['at'], MAX_TIME) and text(event['cause'])
                and type(event['participants']) is list and bool(event['participants'])
                and all(a in state['actors'] for a in event['participants'])
                and len(set(event['participants'])) == len(event['participants']))
        effect = event['effect']
        require(type(effect) is dict and type(effect.get('type')) is str)
        kind = effect['type']
        if kind == 'move':
            fields(effect, {'type', 'actor', 'to'})
            require(effect['actor'] in event['participants'] and effect['to'] in state['locations'])
        elif kind == 'message':
            fields(effect, {'type', 'sender', 'recipient', 'text', 'basis', 'fact'})
            require(effect['sender'] in event['participants'] and effect['recipient'] in event['participants']
                    and effect['sender'] != effect['recipient'] and text(effect['text'])
                    and effect['basis'] in {'hearsay', 'fact'})
            require(effect['fact'] is None if effect['basis'] == 'hearsay'
                    else effect['fact'] in state['facts'])
        elif kind == 'take':
            fields(effect, {'type', 'actor', 'item'})
            require(effect['actor'] in event['participants'] and effect['item'] in state['items'])
        elif kind == 'relationship':
            fields(effect, {'type', 'actor', 'other', 'text'})
            require(effect['actor'] in event['participants'] and effect['other'] in event['participants']
                    and effect['actor'] != effect['other'] and text(effect['text']))
        else:
            require(False, 'invalid_life_effect')
        ids.append(event['id'])
    require(len(ids) == len(set(ids)))
    done = []
    for row in life['history']:
        fields(row, {'id', 'at', 'cause', 'participants', 'status', 'code'})
        require(row['id'] in ids and row['status'] in {'accepted', 'rejected'} and slug(row['code']))
        original = next(e for e in life['queue'] if e['id'] == row['id'])
        require(all(row[k] == original[k] for k in ('at', 'cause', 'participants'))
                and row['at'] <= life['time'])
        done.append(row['id'])
    require(len(done) == len(set(done)))
    ordered = sorted(life['queue'], key=lambda e: (e['at'], e['id']))
    require(done == [e['id'] for e in ordered[:len(done)]])
    require(all(e['at'] >= life['time'] for e in ordered[len(done):]))


def location_at(state, actor, when):
    person = state['life']['people'][actor]
    reachable = {state['actors'][actor]['location']}
    while True:
        expanded = reachable | {place for door in state['doors'].values()
                                if not door['locked'] and reachable.intersection(door['locations'])
                                for place in door['locations']}
        if expanded == reachable:
            break
        reachable = expanded
    latest = None
    for slot in person['schedule']:
        occurrence = (when // 1440) * 1440 + slot['minute']
        if occurrence > when:
            occurrence -= 1440
        if (occurrence > max(person['anchor'], state['life']['time'])
                and slot['location'] in reachable and (latest is None or occurrence > latest[0])):
            latest = (occurrence, slot['location'])
    return latest[1] if latest else state['actors'][actor]['location']


def update_locations(state, when):
    locations = {actor: location_at(state, actor, when) for actor in state['actors']}
    for actor, place in locations.items():
        state['actors'][actor]['location'] = place
    state['life']['time'] = when


def view(state, actor):
    """Own intent/relationships and local groups; no private queue or global history."""
    life = state['life']
    person = life['people'][actor]
    return deepcopy({'time': life['time'], 'goal': person['goal'],
                     'schedule': person['schedule'], 'relations': person['relations'],
                     'origin': person['origin'],
                     'groups': {name: {'count': g['count'], 'role': g['role']}
                                for name, g in life['groups'].items()
                                if g['location'] == state['actors'][actor]['location']}})


def apply_event(state, event):
    """Return a public-safe action summary and private outcome; never invoke a model."""
    e, people = event['effect'], state['life']['people']
    kind = e['type']
    audience = sorted(event['participants'])
    status, code = 'accepted', 'applied'
    if kind == 'move':
        here = state['actors'][e['actor']]['location']
        if here == e['to']:
            status, code = 'rejected', 'invalid_destination'
        elif not any(set(door['locations']) == {here, e['to']} and not door['locked']
                     for door in state['doors'].values()):
            status, code = 'rejected', 'route_blocked'
        else:
            state['actors'][e['actor']]['location'] = e['to']
            people[e['actor']]['anchor'] = event['at']
    elif kind == 'take':
        item, actor = state['items'][e['item']], state['actors'][e['actor']]
        if item['owner'] is not None or item['location'] != actor['location']:
            status, code = 'rejected', 'item_unavailable'
        else:
            item.update(owner=e['actor'], location=None)
    elif kind == 'relationship':
        if e['other'] not in people[e['actor']]['relations'] and len(people[e['actor']]['relations']) >= 32:
            return 'blocked', 'relationship_limit', audience
        people[e['actor']]['relations'][e['other']] = e['text']
    elif kind == 'message':
        fact = state['facts'].get(e['fact'])
        if e['basis'] == 'fact' and e['sender'] not in fact['audience']:
            status, code = 'rejected', 'unknown_fact'
        else:
            memory = state['actors'][e['recipient']]['memory']
            if len(memory) == 256:
                return 'blocked', 'memory_limit', audience
            text = e['text'] if e['basis'] == 'hearsay' else fact['text']
            memory.append({'kind': 'belief' if e['basis'] == 'hearsay' else 'observation',
                           'text': text, 'source': 'message:' + event['id'] + ':' + e['sender']})
            if e['basis'] == 'fact' and e['recipient'] not in fact['audience']:
                fact['audience'] = sorted([*fact['audience'], e['recipient']])
    return status, code, audience
