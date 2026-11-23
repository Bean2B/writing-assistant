"""Book schema extensions used by the public launcher and its worker processes."""
from .operations import exchange
from .story import prior_records, records, scenes, world
from .research import study, trials
from .runtime import tasks, world_adapter

BOOK_FEATURES = (exchange, prior_records, records, scenes, study, trials, world)
SCHEMAS = [feature.SCHEMA for feature in (*BOOK_FEATURES, tasks, world_adapter)]
