"""Configured local-owner boundary over the fixed native World/RunStore."""

from contextlib import contextmanager
import os
from pathlib import Path

from ..core.config import load
from ..core.errors import AssistantError, require
from ..core.files import directory
from ..records.application import owner_store
from . import _facade
from ._continuity import CONFIG_SCHEMA, ContinuityError, RunStore, validate_config
from ._simulation import SimulationError


@contextmanager
def native_errors():
    try:
        yield
    except (ContinuityError, SimulationError, _facade.SandboxError) as error:
        raise AssistantError(error.code) from None


class WorldSession:
    """Local data owner; outputs are not automatically writer-authorized material."""

    def __init__(self, project, owner, scope, root, identity):
        self._project, self._owner, self._scope = project, owner, scope
        self._root, self._identity = root, identity

    def _current(self):
        self._scope.verify()
        with directory(self._root) as fd:
            info = os.fstat(fd)
            require((info.st_dev, info.st_ino) == self._identity and info.st_uid == os.getuid(),
                    "authority_changed")
        return load(self._project)

    def _enabled(self):
        value = self._current()
        require(value["world_sandbox"], "sandbox_disabled")
        return value

    def projection(self, *, actor_id, branch_id="main", purpose="actor-projection", selection=None):
        self._current()
        with native_errors():
            return _facade.projection(self._owner, actor_id=actor_id, branch_id=branch_id,
                                      purpose=purpose, selection=selection)

    def resolve(self, reference, *, actor_id, branch_id="main", purpose="actor-projection", selection=None):
        self._current()
        with native_errors():
            return _facade.resolve_projection(self._owner, reference, actor_id=actor_id,
                                               branch_id=branch_id, purpose=purpose, selection=selection)

    def advance_time(self, *, target, event_limit=16, branch_id="main"):
        self._enabled()
        with native_errors():
            return _facade.advance_time(self._owner, target=target, event_limit=event_limit,
                                        branch_id=branch_id,
                                        stop_requested=lambda: not self._current()["world_sandbox"])

    def fork(self, new_branch_id, *, parent="main"):
        """Create an explicit native branch without changing its parent."""
        self._enabled()
        require(type(new_branch_id) is str and type(parent) is str, "invalid_branch")
        with native_errors():
            return self._owner.fork(new_branch_id, parent=parent)

    def advance(self, *, decision_client, steps=1):
        """Trusted explicit callback boundary; no built-in model or fake decision."""
        initial = self._enabled()
        require(callable(decision_client), "decision_client_required")

        def stopped():
            current = self._current()
            return not current["world_sandbox"] or current["writing_mode"] != initial["writing_mode"]

        def client(raw):
            # Native dispatch may already be marked uncertain here. Refusing a
            # newly disabled call preserves that stage; it never authorizes resend.
            require(not stopped(), "sandbox_disabled")
            try:
                return decision_client(raw)
            except AssistantError as error:
                from ..adapters.codex import CODES
                if error.code in CODES:
                    raise AssistantError(error.code) from None
                raise AssistantError("decision_client_failed") from None
            except Exception:
                raise AssistantError("decision_client_failed") from None

        # Only the native owner lock spans the callback. Configuration updates
        # use a different short-lived lock and can turn the feature off in flight.
        with native_errors():
            return _facade.advance(self._owner, decision_client=client, steps=steps,
                                   stop_requested=stopped)

    def settle(self, *, request_id, branch_id="main"):
        self._current()
        with native_errors():
            return _facade.settle(self._owner, request_id=request_id, branch_id=branch_id)

    def materialize(self, group_id, member_id, actor_id, *, observer, cause_id, branch_id="main"):
        self._enabled()
        with native_errors():
            return self._owner.materialize(group_id, member_id, actor_id, observer=observer,
                                            cause_id=cause_id, branch_id=branch_id)

    def status(self, *, replay=False):
        self._current()
        with native_errors():
            if replay:
                self._owner.replay()
            return {"scope": "owner-progress", "model_calls": 0,
                    "replay_verified": replay, **self._owner.summary()}

    def capture(self, *, actor_id, selection, operation_id, title="", branch_id="main"):
        """Save an explicitly selected historical projection, never world truth."""
        packet = self.projection(actor_id=actor_id, branch_id=branch_id,
                                 purpose="world-projection", selection=selection)
        # Store the selected projection bytes as an immutable historical snapshot.
        store, scope = owner_store(self._project, write=True)
        self._current()
        saved = store.save(scope, operation_id=operation_id, body=packet["body"], title=title,
                           kind="setting", source={"authorship": "unknown",
                           "origin": "World Sandbox projection snapshot " + packet["reference"]["uri"]})
        return {**saved, "projection_reference": packet["reference"], "adopted": False,
                "model_calls": 0}


@contextmanager
def open_run(project, run_id, *, create=False, config=None):
    """Open only this project's explicit data-root namespace and native owner lock."""
    project = Path(os.path.abspath(project))
    _, scope = owner_store(project)
    effective = load(project)
    if create:
        require(effective["world_sandbox"], "sandbox_disabled")
        require(type(config) is dict and config.get("schema") == CONFIG_SCHEMA
                and config.get("policy") == "external", "unsupported_world_config")
        with native_errors():
            validate_config(config)
    else:
        require(config is None, "invalid_request")
    root = Path(effective["data_dir"]) / "world-sandbox" / effective["project_id"] / "runs"
    with directory(root, create=create) as fd:
        info = os.fstat(fd)
        require(info.st_uid == os.getuid(), "data_root_not_owned")
        identity = (info.st_dev, info.st_ino)
    scope.verify()
    with native_errors():
        with RunStore(root, run_id, create=create, config=config) as owner:
            session = WorldSession(project, owner, scope, root, identity)
            session._current()
            yield session
