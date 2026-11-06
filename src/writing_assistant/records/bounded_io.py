"""Bound directory handles for serial version reads without changing storage."""

import os

from .safeio import SafeSession, relative_name


class RecordSession(SafeSession):
    def _read(self, path, *args, **kwargs):
        parts = relative_name(self.root, path)
        version = parts[:-1]
        try:
            return super()._read(path, *args, **kwargs)
        finally:
            # record.json/body.bin handles have already closed in SafeSession.
            # Release only a version's leaf directory, retaining root/project
            # anchors. Every subsequent read reopens and authenticates it.
            if (len(version) == 4 and version[0] == "projects" and version[2] == "versions"
                    and version in self._dirs):
                self._verify_dirs(version)
                handle = self._dirs.pop(version)
                self._dir_anchors.pop(version)
                self._anchors = [entry for entry in self._anchors if entry[1] != handle]
                os.close(handle)
