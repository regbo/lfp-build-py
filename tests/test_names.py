from lfp_build import names


def test_project_name_single_simple_token() -> None:
    assert names.project_name("core") == "core"


def test_project_name_joins_multiple_parts_with_hyphen() -> None:
    assert names.project_name("dbx", "tools", "core") == "dbx-tools-core"


def test_project_name_lowercases_input() -> None:
    assert names.project_name("DBX", "Tools") == "dbx-tools"


def test_project_name_splits_camel_case() -> None:
    assert names.project_name("myProjectName") == "my-project-name"


def test_project_name_handles_acronyms_with_trailing_word() -> None:
    """``HTTPResponse`` should split as ``HTTP`` + ``Response`` (not letter-by-letter)."""
    assert names.project_name("getHTTPResponse") == "get-http-response"


def test_project_name_splits_on_mixed_delimiters() -> None:
    assert names.project_name("My Project_name.foo/bar") == "my-project-name-foo-bar"


def test_project_name_collapses_repeated_delimiters() -> None:
    assert names.project_name("dbx---tools__core") == "dbx-tools-core"


def test_project_name_drops_empty_and_punctuation_only_parts() -> None:
    assert names.project_name("", "core", "  ", "---", "api") == "core-api"


def test_project_name_returns_empty_when_no_alphanumerics() -> None:
    assert names.project_name("", "  ", "---") == ""


def test_project_name_no_args_returns_empty() -> None:
    assert names.project_name() == ""


def test_project_name_keeps_digits_attached_to_letters() -> None:
    assert names.project_name("api", "v2") == "api-v2"


def test_project_name_splits_letter_to_digit_only_at_camel_boundary() -> None:
    """Letter-to-digit (``api2``) is not a camel boundary; digit-to-upper (``v2X``) is."""
    assert names.project_name("api2") == "api2"
    assert names.project_name("v2Beta") == "v2-beta"


def test_module_name_uses_underscore_delimiter() -> None:
    assert names.module_name("dbx-tools", "core") == "dbx_tools_core"


def test_module_name_splits_camel_case() -> None:
    assert names.module_name("MyProject") == "my_project"


def test_module_name_no_args_returns_empty() -> None:
    assert names.module_name() == ""


def test_module_name_parts_preserves_argument_boundaries() -> None:
    assert names.module_name_parts("dbx-tools", "core") == ["dbx_tools", "core"]


def test_module_name_parts_normalizes_each_argument_independently() -> None:
    assert names.module_name_parts("My Project", "API V2") == ["my_project", "api_v2"]


def test_module_name_parts_drops_empty_arguments() -> None:
    assert names.module_name_parts("", "core", "  ", "api") == ["core", "api"]


def test_module_name_parts_returns_empty_list_when_all_inputs_empty() -> None:
    assert names.module_name_parts("", "  ", "---") == []
