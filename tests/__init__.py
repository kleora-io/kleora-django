"""The suite is a package so `tests.settings` is importable by name.

`mypy`'s django plugin imports a settings module to resolve Django's generics
(`[tool.django-stubs] django_settings_module`), and a package with no project of
its own has to supply one. Naming it `tests.settings` means the suite and the
type-checker run against the same file rather than two that can disagree.
"""
