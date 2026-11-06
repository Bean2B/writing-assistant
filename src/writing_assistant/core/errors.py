class AssistantError(ValueError):
    """A stable error code without private file content or provider diagnostics."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise AssistantError(code)
