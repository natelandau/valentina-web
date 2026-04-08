"""String utility functions."""


def human_size(nbytes: float) -> str:
    """Return the human-readable size of a number of bytes.

    Args:
        nbytes: The number of bytes to convert.

    Returns:
        A string of the human-readable size.
    """
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:  # noqa: PLR2004
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"
