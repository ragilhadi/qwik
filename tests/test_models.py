"""Unit tests for qwik core models."""

import pytest

from qwik.core.models import Alias, AliasStore, validate_alias_name


class TestValidateAliasName:
    def test_valid_names(self) -> None:
        assert validate_alias_name("gs") == "gs"
        assert validate_alias_name("gco") == "gco"
        assert validate_alias_name("_private") == "_private"
        assert validate_alias_name("my-alias") == "my-alias"

    def test_invalid_with_space(self) -> None:
        with pytest.raises(ValueError):
            validate_alias_name("my alias")

    def test_invalid_with_slash(self) -> None:
        with pytest.raises(ValueError):
            validate_alias_name("a/b")


class TestAlias:
    def test_creation_defaults(self) -> None:
        a = Alias(command="echo hi")
        assert a.command == "echo hi"
        assert a.tag == []
        assert a.enabled is True
        assert a.run_count == 0

    def test_bump_usage(self) -> None:
        a = Alias(command="echo hi")
        a.bump_usage()
        assert a.run_count == 1
        assert a.last_used is not None

    def test_format_last_used_never(self) -> None:
        a = Alias(command="echo hi")
        assert a.format_last_used() == "never"


class TestAliasStore:
    def test_add_and_get(self) -> None:
        s = AliasStore()
        a = Alias(command="git status")
        s.add("gs", a)
        assert s.get("gs") is a

    def test_add_duplicate_raises(self) -> None:
        s = AliasStore()
        s.add("gs", Alias(command="git status"))
        with pytest.raises(KeyError):
            s.add("gs", Alias(command="git log"))

    def test_add_force_overwrite(self) -> None:
        s = AliasStore()
        s.add("gs", Alias(command="git status"))
        s.add("gs", Alias(command="git log"), force=True)
        assert s.get("gs").command == "git log"

    def test_remove(self) -> None:
        s = AliasStore()
        s.add("gs", Alias(command="git status"))
        removed = s.remove("gs")
        assert removed.command == "git status"
        assert "gs" not in s.aliases

    def test_rename(self) -> None:
        s = AliasStore()
        s.add("gs", Alias(command="git status"))
        s.rename("gs", "gst")
        assert "gst" in s.aliases
        assert "gs" not in s.aliases
