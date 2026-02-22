from apps.core.utils import DivErrorList


def test_div_error_list_includes_dark_mode_classes():
    errors = DivErrorList(["A user is already registered with this email address."])

    rendered = errors.as_divs()

    assert "dark:bg-red-950/40" in rendered
    assert "dark:border-red-500/60" in rendered
    assert "dark:text-red-200" in rendered
    assert "dark:text-red-300" in rendered
