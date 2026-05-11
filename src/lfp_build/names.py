import re

_NON_ALNUM_SPLIT = re.compile(r"[^a-zA-Z0-9]+")
_CAMEL_CASE_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def project_name(*parts: str) -> str:
    return _normalize("-", *parts)


def module_name(*parts: str) -> str:
    return _normalize("_", *parts)


def module_name_parts(*parts: str) -> list[str]:
    return [p for p in (_normalize("_", p) for p in parts) if p]


def _normalize(delimiter: str, *parts: str) -> str:
    normalized_parts = []
    for part in parts:
        if part:
            non_alnum_parts = _NON_ALNUM_SPLIT.split(part)
            for non_alnum_part in non_alnum_parts:
                if non_alnum_part:
                    camel_case_parts = _CAMEL_CASE_SPLIT.split(non_alnum_part)
                    for camel_case_part in camel_case_parts:
                        if camel_case_part:
                            normalized_parts.append(camel_case_part)
    return delimiter.join(normalized_parts).lower()
