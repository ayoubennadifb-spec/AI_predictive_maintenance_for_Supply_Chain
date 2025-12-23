class PipelineStepError(RuntimeError):
    """Raised when a pipeline step fails; carries the in-progress state."""

    def __init__(self, message: str, state):
        super().__init__(message)
        self.state = state
