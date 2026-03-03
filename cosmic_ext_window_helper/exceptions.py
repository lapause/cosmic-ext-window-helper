class HelperError(Exception):
    """Generic module exception"""

    def __init__(self, msg: str, details: str = ""):
        super().__init__(msg)
        self.msg = msg
        self.exit_code = 10
        self.details = details
