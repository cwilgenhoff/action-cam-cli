"""Custom exception types.

Domain code (``core/``, ``grading/``) raises these instead of calling
``sys.exit()``; the CLI layer (``cli.py``) catches them, prints to stderr, and
translates them into process exit codes. See ADR 0002.
"""


class PipelineError(Exception):
    """A fatal, user-facing pipeline error.

    The string message is the exact text to show the user on stderr (it may span
    multiple lines). The CLI prints it verbatim and exits non-zero.
    """
