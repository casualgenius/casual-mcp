class GenerationError(Exception):
    """Exception raised for custom error scenarios.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)
