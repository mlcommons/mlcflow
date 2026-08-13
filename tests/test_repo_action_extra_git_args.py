from mlc.repo_action import RepoAction


def test_validate_extra_git_args_allows_literal_shell_characters():
    assert RepoAction._validate_extra_git_args(
        [
            "refs/pull/$PR/head",
            "http.extraHeader=Authorization: ******",
            "name-with|pipe",
            "`literal-backticks`",
        ]
    ) is None


def test_validate_extra_git_args_rejects_line_breaks():
    error = RepoAction._validate_extra_git_args(["line1\nline2"])

    assert error == (
        "--extra_git_args may not include carriage returns or newlines."
    )
