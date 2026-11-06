"""Local data-owner CLI scope. No deserialized role grants are accepted."""

import os
from pathlib import Path

from ..core.config import load
from ..core.errors import require
from ..core.files import directory
from .core import RecordStore, Scope


def owner_store(project, *, write=False, resolver=None):
    config = load(project)
    root = Path(config["data_dir"])
    # Explicitly invoking the local CLI for an initialized project is the local
    # data-owner operation. This is not an authentication scheme for a service.
    with directory(root) as fd:
        info = os.fstat(fd)
        require(info.st_uid == os.getuid(), "data_root_not_owned")
        identity = (info.st_dev, info.st_ino)

    def check():
        current = load(project)
        require(current["project_id"] == config["project_id"] and current["data_dir"] == str(root), "authority_changed")
        with directory(root) as fd:
            found = os.fstat(fd)
            require((found.st_dev, found.st_ino) == identity and found.st_uid == os.getuid(), "authority_changed")

    return RecordStore(root, resolver=resolver), Scope(config["project_id"], "owner", check, writable=write)


def artifact_resolver(root, values):
    """Bind explicitly selected local owner files; never discover producer data."""
    from .adapters import ArtifactBinding, BoundArtifacts
    from .core import keys, require as record_require

    root = Path(os.path.abspath(root))
    record_require(isinstance(values, list) and len(values) <= 128, "invalid_schema")
    with directory(root) as fd:
        info = os.fstat(fd)
        identity = (info.st_dev, info.st_ino)
    bindings = []
    for value in values:
        keys(value, "project_id audiences descriptor relative_path")
        record_require(isinstance(value["audiences"], list), "invalid_schema")
        bindings.append(ArtifactBinding(value["project_id"], frozenset(value["audiences"]),
                                        value["descriptor"], value["relative_path"]))
    bound = BoundArtifacts(root, bindings)

    def resolve(descriptor, scope):
        scope.verify()
        with directory(root) as fd:
            current = os.fstat(fd)
            require((current.st_dev, current.st_ino) == identity, "authority_changed")
        return bound(descriptor, scope)

    return resolve


def material_resolver(project, values, *, resolver=None):
    """Map explicit transport URIs to exact records in this local owner scope."""
    from .core import keys, ref_key, require as record_require

    record_require(isinstance(values, list) and len(values) <= 32, "invalid_schema")
    selected = {}
    for value in values:
        keys(value, "uri ref")
        record_require(isinstance(value["uri"], str) and 0 < len(value["uri"]) <= 2048
                       and value["uri"] not in selected, "invalid_schema")
        ref_key(value["ref"])
        selected[value["uri"]] = dict(value["ref"])
    store, scope = owner_store(project, resolver=resolver)

    def resolve(reference):
        scope.verify()
        record_require(reference["uri"] in selected, "not_available")
        ref = selected[reference["uri"]]
        record_require(ref["sha256"] == reference["sha256"], "stale_reference")
        return store.read(scope, ref)["body"]

    return resolve
