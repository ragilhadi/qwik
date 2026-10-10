"""Tests for secret-shaped command redaction (issue #36).

The corpus here doubles as documentation of what ``qwik suggest``
refuses to suggest. Every entry in ``SECRET_CORPUS`` must match;
everything in ``SAFE_CORPUS`` must not (no false positives on ordinary
commands). Deliberately over-inclusive is fine — a false positive costs
one suggestion, a false negative leaks a credential.
"""

from __future__ import annotations

import pytest

from qwik.core.redact import contains_secret, redact_command

SECRET_CORPUS = [
    "mysql -u root -p s3cretpass mydb",
    "psql postgresql://admin:hunter2@db.example.com/prod",
    "ssh -i ~/.ssh/id_rsa server@host",
    "git push https://user:ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX@github.com/repo",
    "export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI",
    "export API_KEY=sk-proj-XXXXXXXXXXXXXXXXXXXX",
    (
        "curl -H 'Authorization: Bearer "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c'"
    ),
    "aws configure set aws_secret_access_key wJalrXUtnFEMI/K7MDENG/bPxRfiCY",
    "sudo openvpn --config corp --auth-user-pass passfile",
    "gpg --passphrase 'luggage code' --decrypt file.gpg",
    "kubectl create secret generic db --from-literal=password=xyz",
    "sshpass -p hunter2 scp file server:/tmp",
    "security add-generic-password -s svc -a me -w hunter2",
    "curl -u admin:s3cret https://api.example.com",
    "AKIAIOSFODNN7EXAMPLE s3 ls",
    "openssl passwd -1 'mypassword'",
    "dotnet user-secrets set 'Db:Password' 'hunter2'",
    "export MY_TOKEN=glpat-XXXX",
    "login with --password=hunter2 to proceed",
    "openssl genrsa -out id_rsa 2048",
]

SAFE_CORPUS = [
    "git status",
    "git push origin main",
    "docker compose up -d",
    "kubectl get pods -n production",
    "ls -la",
    "echo hello world",
    "npm run build --silent",
    "cargo build --release",
    "pip install -r requirements.txt",
    "grep -r 'pattern' src/",
    "tar -xzvf archive.tar.gz",
    "systemctl status nginx",
    "find . -name '*.py' -type f",
    "curl https://api.example.com/health",
    "python -m pytest tests/",
    "make clean all",
    "aws s3 ls",  # aws without a secret-shaped value is fine
    "ssh server@host",  # key-based ssh without -i id_rsa
]


@pytest.mark.parametrize("command", SECRET_CORPUS, ids=lambda c: c[:30])
def test_secret_commands_detected(command: str) -> None:
    assert contains_secret(command), f"not detected: {command!r}"


@pytest.mark.parametrize("command", SAFE_CORPUS, ids=lambda c: c[:30])
def test_safe_commands_pass(command: str) -> None:
    assert not contains_secret(command), f"false positive: {command!r}"


def test_redact_command_hides_content() -> None:
    out = redact_command("mysql -u root -p hunter2")
    assert "hunter2" not in out
    assert "mysql" in out


def test_redact_command_empty() -> None:
    assert "redacted" in redact_command("")


def test_redact_truncates_long_first_word() -> None:
    out = redact_command("a" * 100 + " -p secret")
    assert len(out) < 60
