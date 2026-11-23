"""Deterministic population, recurring appointments and explicitly caused encounters."""
import copy


FIELDS = {
    "encounter": ("actor", "group", "member"),
    "move": ("actor", "location"),
    "relationship": ("actor", "other", "relation"),
    "message": ("actor", "other", "key", "text", "certainty"),
    "take": ("actor", "resource"),
}


def shape(value, required, optional=()):
    if not isinstance(value, dict) or set(required) - value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError("Unexpected or missing life field.")


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Life names, causes and labels must be nonempty text.")
    return value


def names(values):
    if not isinstance(values, list) or len(set(map(text, values))) != len(values):
        raise ValueError("Expected a list of distinct names.")


def person_spec(person, locations, ids):
    shape(person, ("location", "goal"), ("schedule", "relations"))
    text(person["goal"])
    if text(person["location"]) not in locations:
        raise ValueError("Unknown initial location.")
    slots = person.get("schedule", [])
    if not isinstance(slots, list) or len(slots) > 16:
        raise ValueError("Schedules allow up to 16 daily appointments.")
    seen = set()
    for slot in slots:
        shape(slot, ("minute", "location"))
        minute = slot["minute"]
        if type(minute) is not int or not 0 <= minute < 1440 or minute in seen or text(slot["location"]) not in locations:
            raise ValueError("Invalid recurring appointment.")
        seen.add(minute)
    rel = person.get("relations", {})
    if not isinstance(rel, dict) or len(rel) > 32 or set(rel) - ids:
        raise ValueError("Invalid directed relationships.")
    for desc in rel.values():
        text(desc)


def validate(life, participants):
    shape(life, ("locations", "people"), ("routes", "groups", "events", "resources"))
    names(life["locations"])
    locs = set(life["locations"])
    people, groups = life["people"], life.get("groups", {})
    if (not isinstance(people, dict) or not 1 <= len(people) <= 128 or set(participants) - people.keys()
            or not isinstance(groups, dict) or len(groups) > 16 or set(groups) & set(people)):
        raise ValueError("Life requires 1–128 named people, including all decision participants, and up to 16 groups.")
    for name, person in people.items():
        text(name)
        person_spec(person, locs, set(people))
    total = 0
    for name, group in groups.items():
        text(name)
        shape(group, ("location", "count"))
        if text(group["location"]) not in locs or type(group["count"]) is not int or group["count"] < 0:
            raise ValueError("Invalid aggregate population.")
        total += group["count"]
    if total > 1000:
        raise ValueError("Aggregate groups allow up to 1,000 unnamed members.")
    routes = life.get("routes", [])
    if not isinstance(routes, list):
        raise ValueError("Expected a list of routes.")
    edges = set()
    for route in routes:
        shape(route, ("from", "to"), ("open",))
        ends = frozenset([text(route["from"]), text(route["to"])])
        if len(ends) != 2 or ends - locs or ends in edges or type(route.get("open", True)) is not bool:
            raise ValueError("Invalid world route.")
        edges.add(ends)
    resources = life.get("resources", {})
    if not isinstance(resources, dict) or any(text(loc) not in locs for loc in resources.values()):
        raise ValueError("Resource must have a known starting location.")
    for key in resources:
        text(key)
    events = life.get("events", [])
    if not isinstance(events, list) or len(events) > 128:
        raise ValueError("Supply up to 128 causal events.")
    event_ids = set()
    for event in events:
        kind = event.get("kind") if isinstance(event, dict) else None
        if not isinstance(kind, str) or kind not in FIELDS:
            raise ValueError("Unsupported causal event.")
        shape(event, ("id", "at", "kind", "cause", *FIELDS[kind]))
        for key in ("id", "cause", *FIELDS[kind]):
            text(event[key])
        if type(event["at"]) is not int or not 1 <= event["at"] <= 1000000 or event["id"] in event_ids:
            raise ValueError("Invalid or duplicate causal event.")
        event_ids.add(event["id"])
        if event["actor"] not in people or ("other" in event and event["other"] not in people):
            raise ValueError("Unknown participant in causal event.")
        if (kind == "encounter" and event["group"] not in groups or
                kind == "move" and event["location"] not in locs or
                kind == "take" and event["resource"] not in resources or
                kind == "message" and event["certainty"] not in ("fact", "belief")):
            raise ValueError("Invalid causal event target.")


def initial(definition):
    people = copy.deepcopy(definition["people"])
    for person in people.values():
        person.setdefault("relations", {})
        person.setdefault("schedule", [])
        person.update(memory={}, origin=None)
    routes = {loc: set() for loc in definition["locations"]}
    for edge in definition.get("routes", []):
        if edge.get("open", True):
            routes[edge["from"]].add(edge["to"])
            routes[edge["to"]].add(edge["from"])
    reachable = {}
    for loc in routes:
        if loc in reachable:
            continue
        component, pending = {loc}, [loc]
        while pending:
            near = routes[pending.pop()] - component
            pending.extend(near)
            component.update(near)
        for member in component:
            reachable[member] = component
    return {"people": people, "groups": copy.deepcopy(definition.get("groups", {})),
            "resources": {name: {"location": loc, "owner": None} for name, loc in definition.get("resources", {}).items()},
            "routes": routes, "reachable": reachable, "queue": sorted(definition.get("events", []),
                                                                     key=lambda e: (e["at"], e["id"])),
            "cursor": 0, "history": [], "origins": {}}


def appointments(life, start, end):
    if end == start:
        return
    for person in life["people"].values():
        latest, chosen = start, person["location"]
        reachable = life["reachable"][chosen]
        for slot in person["schedule"]:
            occurrence = end - ((end - slot["minute"]) % 1440)
            if latest < occurrence and slot["location"] in reachable:
                latest, chosen = occurrence, slot["location"]
        person["location"] = chosen


def cause(life, event, state):
    who, kind = event["actor"], event["kind"]
    person = life["people"][who]
    location = person["location"]
    witnesses = [who]
    accepted = False
    if kind == "encounter":
        group = life["groups"][event["group"]]
        accepted = group["count"] > 0 and location == group["location"]
    elif kind == "move":
        if event["location"] in life["routes"][location]:
            person["location"] = event["location"]
            accepted = True
    elif kind == "relationship":
        other = event["other"]
        if life["people"][other]["location"] == location:
            if other not in person["relations"] and len(person["relations"]) >= 32:
                return "relationship-capacity"
            person["relations"][other] = event["relation"]
            accepted = True
    elif kind == "message":
        other, key = event["other"], event["key"]
        target = life["people"][other]["memory"]
        source = person["memory"].get(key, {})
        known = (state["actors"].get(who, {}).get(key) == event["text"] or state["public"].get(key) == event["text"]
                 or source.get("certainty") == "fact" and source.get("text") == event["text"])
        if event["certainty"] == "belief" or known:
            if key not in target and len(target) >= 256:
                return "memory-capacity"
            target[key] = {"certainty": event["certainty"], "text": event["text"], "from": who, "source": event["id"]}
            witnesses.append(other)
            accepted = True
    elif kind == "take":
        item = life["resources"][event["resource"]]
        if item["owner"] is None and item["location"] == location:
            item.update(owner=who, location=None)
            accepted = True
    entry = {"id": event["id"], "kind": kind, "at": event["at"], "cause": event["cause"],
             "actor": who, "location": location, "witnesses": witnesses, "accepted": accepted}
    entry.update({field: event[field] for field in FIELDS[kind] if field != "actor"})
    life["history"].append(entry)


def advance(state, target, limit, move_clock):
    """Apply schedules only at causal boundaries and the selected endpoint."""
    life = state["life"]
    cursor = life["cursor"]
    due = [e for e in life["queue"][cursor:] if e["at"] <= target]
    processed = []
    blocked = None
    for event in due[:limit]:
        appointments(life, state["minute"], event["at"])
        move_clock(event["at"])
        blocked = cause(life, event, state)
        if blocked:
            break
        processed.append(event["id"])
        life["cursor"] += 1
    if len(processed) == len(due):
        appointments(life, state["minute"], target)
        move_clock(target)
    remaining = len(due) - len(processed)
    return {"processed": processed, "remaining_due": remaining, "paused": bool(remaining), "blocked": blocked}


def population(life):
    named = len(life["people"])
    unnamed = sum(g["count"] for g in life["groups"].values())
    return {"named": named, "unnamed": unnamed, "total": named + unnamed}


def observation(life, actor):
    person = life["people"][actor]
    loc = person["location"]
    return {"location": loc, "goal": person["goal"], "schedule": person["schedule"], "relations": person["relations"],
            "memory": person["memory"], "origin": person["origin"],
            "nearby": sorted(n for n, p in life["people"].items() if n != actor and p["location"] == loc),
            "groups": {g: x["count"] for g, x in life["groups"].items() if x["location"] == loc},
            "resources": sorted(k for k, x in life["resources"].items() if x["owner"] == actor or x["location"] == loc),
            "events": [{k: e[k] for k in ("id", "kind", "at", "accepted")}
                       for e in life["history"] if actor in e["witnesses"]]}


def existing(life, event):
    key = event["group"], event["member"]
    prior = life["origins"].get(key)
    if prior and any(prior.get(field) != event[field] for field in ("observer", "cause", "person")):
        raise ValueError("This group member already has another recorded identity or origin.")
    return prior is not None


def materialize(life, event):
    if existing(life, event):
        return
    group = life["groups"].get(event["group"])
    person = life["people"].get(event["observer"])
    if group is None or person is None or group["count"] < 1 or group["location"] != person["location"]:
        raise ValueError("Naming requires a present group member and a colocated observer.")
    if event["person"] in life["people"] or event["person"] in life["groups"] or len(life["people"]) >= 128:
        raise ValueError("Named identity already used or named population limit reached.")
    matching = any(e["id"] == event["cause"] and e["kind"] == "encounter" and e["accepted"]
                   and e["actor"] == event["observer"] and e["group"] == event["group"]
                   and e["member"] == event["member"] and e["location"] == group["location"]
                   for e in life["history"])
    if not matching:
        raise ValueError("No recorded encounter ties this observer to this group member here.")
    group["count"] -= 1
    # Group membership conveys a place and an origin. It conveys no old private history.
    origin = {key: event[key] for key in ("group", "member", "observer", "cause")}
    life["people"][event["person"]] = {"location": group["location"], "goal": None, "relations": {},
                                      "schedule": [], "memory": {}, "origin": origin}
    life["origins"][event["group"], event["member"]] = dict(event)
