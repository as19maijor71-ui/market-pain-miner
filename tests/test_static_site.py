from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import pytest

from app.cli import (
    load_project_profile,
    project_profile_template_payload,
    run_classify,
    run_import,
    run_profile_template,
    run_site,
    validate_project_profile_template_path,
    validate_site_dir_path,
)


FIXTURE = Path(__file__).parent / "fixtures" / "telegram_solutions_result.json"


@contextmanager
def temporary_db_path() -> Iterator[Path]:
    db_path = Path(__file__).parent / f"_tmp_site_{uuid4().hex}.sqlite"
    try:
        yield db_path
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{db_path}{suffix}")
            if candidate.exists():
                candidate.unlink()


@contextmanager
def temporary_site_dir() -> Iterator[Path]:
    site_dir = Path(__file__).parent / f"_tmp_site_{uuid4().hex}"
    try:
        yield site_dir
    finally:
        if site_dir.exists():
            shutil.rmtree(site_dir)


@contextmanager
def temporary_profile_path(payload: object) -> Iterator[Path]:
    profile_path = Path(__file__).parent / f"_tmp_profile_{uuid4().hex}.json"
    try:
        profile_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        yield profile_path
    finally:
        if profile_path.exists():
            profile_path.unlink()


@contextmanager
def temporary_profile_output_path() -> Iterator[Path]:
    profile_path = Path(__file__).parent / f"_tmp_profile_template_{uuid4().hex}.json"
    try:
        yield profile_path
    finally:
        if profile_path.exists():
            profile_path.unlink()


def test_static_site_generates_pages_data_and_safe_content(capsys) -> None:
    with temporary_db_path() as db_path, temporary_site_dir() as site_dir:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        result = run_site(
            db_path,
            site_dir,
            limit=10,
            project_name="Market Pain Miner",
        )
        output = capsys.readouterr().out

        expected_files = {
            "index.html",
            "people.html",
            "tools.html",
            "insights.html",
            "niches.html",
            "for-you.html",
            "favicon.svg",
            "css/style.css",
            "data/summary.json",
            "data/participants.json",
            "data/tools.json",
            "data/insights.json",
            "data/niches.json",
            "data/for-you.json",
            "data/chat_meta.json",
        }
        for relative in expected_files:
            assert (site_dir / relative).exists(), relative

        for relative in expected_files:
            if relative.startswith("data/"):
                json.loads((site_dir / relative).read_text(encoding="utf-8"))

        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in site_dir.rglob("*")
            if path.is_file() and path.suffix in {".html", ".json", ".css", ".svg"}
        )

    assert "Static site generated" in output
    assert result["path"].endswith(site_dir.name)
    assert "python -m http.server 8765" in output
    assert "Для тебя" in combined
    assert "participants.json" in combined
    assert "tools.json" in combined
    assert "chat1:1" in combined

    assert "Synthetic Solutions Fixture" not in combined
    assert "synthetic_participant" not in combined
    assert "3000000000" not in combined
    assert "https://sellerstock.test" not in combined
    assert "sellerstock.test" not in combined
    assert "@StockPilot" not in combined
    assert "Не могу свести" not in combined
    assert "Рекомендую бот" not in combined


def test_static_site_uses_local_project_profile(capsys) -> None:
    profile = {
        "project_name": "Safe Pilot",
        "project_summary": "Локальная проверка research bot.",
        "user": "owner",
        "target_segments": ["WB seller", "marketplace manager"],
        "focus_themes": ["reviews", "penalties"],
        "avoid_themes": ["stock"],
        "offer_types": ["audit report", "telegram alert"],
        "decision_criteria": ["visible pain", "manual repetition"],
        "design_preferences": ["local-first", "privacy-safe"],
        "next_questions": ["Какие evidence открыть первыми?"],
    }
    with (
        temporary_db_path() as db_path,
        temporary_site_dir() as site_dir,
        temporary_profile_path(profile) as profile_path,
    ):
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        result = run_site(
            db_path,
            site_dir,
            limit=10,
            project_profile_path=profile_path,
        )
        output = capsys.readouterr().out
        for_you = json.loads((site_dir / "data/for-you.json").read_text(encoding="utf-8"))
        index_html = (site_dir / "index.html").read_text(encoding="utf-8")
        for_you_html = (site_dir / "for-you.html").read_text(encoding="utf-8")

    assert result["payload"]["project"]["name"] == "Safe Pilot"
    assert "project_profile=" in output
    assert "Safe Pilot" in index_html
    assert "Фокус Проекта" in for_you_html
    assert for_you["project_profile"]["focus_themes"] == ["reviews", "penalties"]
    assert for_you["project_profile"]["target_segments"] == [
        "WB seller",
        "marketplace manager",
    ]
    assert "audit report" in json.dumps(for_you, ensure_ascii=False)
    assert "Какие evidence открыть первыми?" in json.dumps(
        for_you,
        ensure_ascii=False,
    )


def test_project_profile_focus_themes_create_profile_matches(capsys) -> None:
    profile = {
        "project_name": "Focus Pilot",
        "project_summary": "Локальная проверка profile matching.",
        "focus_themes": ["stock"],
        "avoid_themes": [],
        "next_questions": ["Какие stock aliases открыть первыми?"],
    }
    with (
        temporary_db_path() as db_path,
        temporary_site_dir() as site_dir,
        temporary_profile_path(profile) as profile_path,
    ):
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        run_site(
            db_path,
            site_dir,
            limit=10,
            project_profile_path=profile_path,
        )
        for_you = json.loads((site_dir / "data/for-you.json").read_text(encoding="utf-8"))
        for_you_html = (site_dir / "for-you.html").read_text(encoding="utf-8")
        for relative in (site_dir / "data").glob("*.json"):
            json.loads(relative.read_text(encoding="utf-8"))

    assert "Совпадения С Фокусом" in for_you_html
    assert "Следующая Проверка" in for_you_html
    assert "Команды Review" in for_you_html
    assert for_you["profile_matches"]
    assert any(
        item["type"] == "opportunity" and item["matched_themes"] == ["stock"]
        for item in for_you["profile_matches"]
    )
    assert any(
        item["type"] == "theme" and item["matched_themes"] == ["stock"]
        for item in for_you["profile_matches"]
    )
    assert 3 <= len(for_you["recommended_next_review"]) <= 7
    assert for_you["now"][0]["priority"] == "P0"
    assert "profile_focus=stock" in for_you["now"][0]["why"]
    assert all(
        alias.startswith("chat")
        for item in for_you["profile_matches"]
        for alias in item["evidence_aliases"]
    )
    assert for_you["review_commands"]
    review_command = for_you["review_commands"][0]
    assert review_command["evidence_alias"].startswith("chat")
    assert review_command["evidence_alias"] in review_command["command"]
    assert review_command["suggested_category"] == "pain"
    assert review_command["suggested_topics"] == ["stock"]
    assert "--set-label" in review_command["command"]
    assert " pain" in review_command["command"]
    assert "--topics stock" in review_command["command"]
    assert "<local-db-path>" in review_command["command"]
    assert "<local-db-path>" in review_command["followup_command"]
    assert "<local-site-dir>" in review_command["followup_command"]
    assert "<local-profile-path>" in review_command["followup_command"]

    serialized_commands = json.dumps(for_you["review_commands"], ensure_ascii=False)
    assert "Synthetic Solutions Fixture" not in serialized_commands
    assert "synthetic_participant" not in serialized_commands
    assert "3000000000" not in serialized_commands
    assert "https://sellerstock.test" not in serialized_commands
    assert "sellerstock.test" not in serialized_commands
    assert "@StockPilot" not in serialized_commands
    assert "Не могу свести" not in serialized_commands
    assert "Рекомендую бот" not in serialized_commands


def test_static_site_cli_command_hints_feed_review_commands(capsys) -> None:
    profile = {
        "project_name": "Command Pilot",
        "project_summary": "Локальная проверка command hints.",
        "focus_themes": ["stock"],
        "avoid_themes": [],
    }
    with (
        temporary_db_path() as db_path,
        temporary_site_dir() as site_dir,
        temporary_profile_path(profile) as profile_path,
    ):
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.cli",
                "--db",
                str(db_path),
                "site",
                "--output-dir",
                str(site_dir),
                "--project-profile",
                str(profile_path),
                "--db-command-path",
                "data/db/pilot-001.sqlite",
                "--site-command-path",
                "data/reports/pilot-001-site",
                "--profile-command-path",
                "data/reports/project-profile.json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        for_you = json.loads((site_dir / "data/for-you.json").read_text(encoding="utf-8"))

    assert for_you["review_commands"]
    review_command = for_you["review_commands"][0]
    assert "data/db/pilot-001.sqlite" in review_command["command"]
    assert "data/db/pilot-001.sqlite" in review_command["followup_command"]
    assert "data/reports/pilot-001-site" in review_command["followup_command"]
    assert "data/reports/project-profile.json" in review_command["followup_command"]
    assert "<local-db-path>" not in review_command["command"]
    assert "<local-site-dir>" not in review_command["followup_command"]
    assert "<local-profile-path>" not in review_command["followup_command"]


def test_project_profile_avoid_themes_warn_and_lower_priority(capsys) -> None:
    profile = {
        "project_name": "Avoid Pilot",
        "project_summary": "Локальная проверка avoid_themes.",
        "focus_themes": ["stock"],
        "avoid_themes": ["stock"],
    }
    with (
        temporary_db_path() as db_path,
        temporary_site_dir() as site_dir,
        temporary_profile_path(profile) as profile_path,
    ):
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        run_site(
            db_path,
            site_dir,
            limit=10,
            project_profile_path=profile_path,
        )
        for_you = json.loads((site_dir / "data/for-you.json").read_text(encoding="utf-8"))

    warning_codes = {item["code"] for item in for_you["profile_warnings"]}
    assert "avoid_themes_detected" in warning_codes
    assert "all_matches_only_in_avoid_themes" in warning_codes
    assert for_you["profile_matches"]
    assert {item["priority"] for item in for_you["profile_matches"]} == {"P2"}
    assert for_you["now"][0]["priority"] == "P2"
    assert for_you["profile_matches"][0]["evidence_aliases"]


def test_empty_project_profile_keeps_static_site_flow(capsys) -> None:
    with temporary_db_path() as db_path, temporary_site_dir() as site_dir:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        run_site(db_path, site_dir, limit=10)
        for_you = json.loads((site_dir / "data/for-you.json").read_text(encoding="utf-8"))

    assert for_you["project_profile"]["focus_themes"] == []
    assert for_you["profile_matches"] == []
    assert for_you["review_commands"] == []
    assert any(
        item["code"] == "focus_themes_empty"
        for item in for_you["profile_warnings"]
    )
    assert for_you["now"]
    assert for_you["project_fit"]
    assert 3 <= len(for_you["recommended_next_review"]) <= 7


def test_profile_matching_output_stays_privacy_safe(capsys) -> None:
    profile = {
        "project_name": "Privacy Pilot",
        "project_summary": "Локальная проверка privacy-safe output.",
        "focus_themes": ["stock"],
        "avoid_themes": ["stock"],
    }
    with (
        temporary_db_path() as db_path,
        temporary_site_dir() as site_dir,
        temporary_profile_path(profile) as profile_path,
    ):
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        run_site(
            db_path,
            site_dir,
            limit=10,
            project_profile_path=profile_path,
        )
        serialized = json.dumps(
            json.loads((site_dir / "data/for-you.json").read_text(encoding="utf-8")),
            ensure_ascii=False,
        )
        html = (site_dir / "for-you.html").read_text(encoding="utf-8")
        combined = serialized + "\n" + html

    assert "Synthetic Solutions Fixture" not in combined
    assert "synthetic_participant" not in combined
    assert "3000000000" not in combined
    assert "https://sellerstock.test" not in combined
    assert "sellerstock.test" not in combined
    assert "@StockPilot" not in combined
    assert "Не могу свести" not in combined
    assert "Рекомендую бот" not in combined


def test_project_profile_rejects_invalid_json_shape() -> None:
    with temporary_profile_path(["not", "an", "object"]) as profile_path:
        with pytest.raises(ValueError, match="JSON object"):
            load_project_profile(profile_path)


def test_profile_template_cli_creates_privacy_safe_json() -> None:
    with temporary_profile_output_path() as profile_path:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.cli",
                "profile-template",
                "--output",
                str(profile_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        loaded_profile = load_project_profile(profile_path)
        serialized = json.dumps(payload, ensure_ascii=False)

    assert "Project profile template created" in completed.stdout
    assert payload == project_profile_template_payload()
    assert loaded_profile["focus_themes"] == ["reviews", "penalties", "automation"]
    assert loaded_profile["target_segments"] == [
        "WB/Ozon seller",
        "marketplace manager",
    ]
    assert "@" not in serialized
    assert "http://" not in serialized
    assert "https://" not in serialized
    assert "pilot-" not in serialized
    assert "synthetic_participant" not in serialized
    assert "3000000000" not in serialized


def test_profile_template_refuses_overwrite_without_force() -> None:
    with temporary_profile_output_path() as profile_path:
        run_profile_template(profile_path)

        with pytest.raises(ValueError, match="already exists"):
            run_profile_template(profile_path)

        result = run_profile_template(profile_path, force=True)

    assert result["path"].endswith(profile_path.name)


def test_profile_template_path_rejects_trackable_output_by_default() -> None:
    validate_project_profile_template_path(Path("tests/_tmp_safe_profile.json"))
    validate_project_profile_template_path(
        Path("local-profile.json"),
        allow_external_profile=True,
    )

    with pytest.raises(ValueError, match="outside data/reports"):
        validate_project_profile_template_path(Path("project-profile.json"))

    with pytest.raises(ValueError, match="must end with .json"):
        validate_project_profile_template_path(Path("data/reports/project-profile.txt"))


def test_site_dir_rejects_trackable_output_by_default() -> None:
    validate_site_dir_path(Path("tests/_tmp_safe_site"))
    validate_site_dir_path(Path("external-site"), allow_external_site=True)

    with pytest.raises(ValueError, match="outside data/reports"):
        validate_site_dir_path(Path("public-site"))

    with pytest.raises(ValueError, match="directory path"):
        validate_site_dir_path(Path("data/reports/site.html"))
