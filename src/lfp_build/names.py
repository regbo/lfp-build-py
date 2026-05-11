import re

"""
Canonical name helpers used across lfp-build.

Inputs are tokenized in two passes before being lowercased and joined:

1. Split on runs of non-alphanumeric characters (whitespace, ``-``, ``_``,
   ``.``, ``/``, etc.) so callers can pass arbitrary user-supplied strings
   without first sanitizing them.
2. Split each surviving token on camelCase / PascalCase boundaries so
   identifiers like ``getHTTPResponse`` round-trip cleanly into
   ``get-http-response`` rather than collapsing into one word.

The three public helpers differ only in how the resulting tokens are
emitted:

- :func:`project_name` joins them with ``-`` (PEP 503-style project name).
- :func:`module_name` joins them with ``_`` (importable Python identifier).
- :func:`module_name_parts` normalizes each ``parts`` argument independently
  and returns the per-argument tokens as a list of underscore-joined
  strings - handy for building nested module paths like
  ``["dbx_tools", "core"]`` from ``("dbx-tools", "core")``.
"""

# Splits on any run of non-alphanumeric characters so we can normalize
# strings that mix delimiters (e.g. ``"My Project / Foo_bar"``).
_NON_ALNUM_SPLIT = re.compile(r"[^a-zA-Z0-9]+")

# Splits on camelCase / PascalCase boundaries. The first alternative
# catches ``aB`` (lower/digit -> upper); the second catches the
# acronym-to-word transition in patterns like ``HTTPResponse`` where an
# uppercase run is followed by an uppercase + lowercase pair.
_CAMEL_CASE_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def project_name(*parts: str) -> str:
    """
    Build a canonical project (distribution) name from ``parts``.

    The resulting string is lowercase and uses ``-`` between tokens, e.g.
    ``project_name("dbx-tools", "core") == "dbx-tools-core"``. Empty or
    whitespace-only parts are dropped. Returns ``""`` if every part
    reduces to nothing.
    """
    return _normalize("-", *parts)


def module_name(*parts: str) -> str:
    """
    Build a canonical Python module name from ``parts``.

    The resulting string is lowercase and uses ``_`` between tokens, e.g.
    ``module_name("dbx-tools", "core") == "dbx_tools_core"``. Behaves
    identically to :func:`project_name` aside from the delimiter and is
    safe to use as a Python identifier when at least one alphanumeric
    character is present.
    """
    return _normalize("_", *parts)


def module_name_parts(*parts: str) -> list[str]:
    """
    Normalize each argument independently and return the surviving tokens.

    Unlike :func:`module_name`, this preserves the boundary between
    arguments. Each ``parts[i]`` is run through :func:`module_name` on
    its own, and empty results are dropped. Useful when the caller wants
    to assemble a nested module path or write each segment separately,
    e.g. ``module_name_parts("dbx-tools", "core") == ["dbx_tools", "core"]``.
    """
    return [p for p in (_normalize("_", p) for p in parts) if p]


def _normalize(delimiter: str, *parts: str) -> str:
    """
    Tokenize ``parts``, lowercase the result, and join with ``delimiter``.

    Performs the two-pass split described in the module docstring:
    non-alphanumeric runs first, then camelCase boundaries. Empty
    intermediate fragments are skipped so consecutive delimiters in the
    input do not produce empty tokens in the output.
    """
    normalized_parts = []
    for part in parts:
        if part:
            non_alnum_parts = _NON_ALNUM_SPLIT.split(part)
            for non_alnum_part in (p.strip() for p in non_alnum_parts):
                if non_alnum_part:
                    camel_case_parts = _CAMEL_CASE_SPLIT.split(non_alnum_part)
                    for camel_case_part in (p.strip() for p in camel_case_parts):
                        if camel_case_part:
                            normalized_parts.append(camel_case_part)
    return delimiter.join(normalized_parts).lower()
