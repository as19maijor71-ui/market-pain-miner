from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from app.cli import (
    load_project_profile,
    run_classify,
    run_import,
    run_site,
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


def test_project_profile_rejects_invalid_json_shape() -> None:
    with temporary_profile_path(["not", "an", "object"]) as profile_path:
        with pytest.raises(ValueError, match="JSON object"):
            load_project_profile(profile_path)


def test_site_dir_rejects_trackable_output_by_default() -> None:
    validate_site_dir_path(Path("tests/_tmp_safe_site"))
    validate_site_dir_path(Path("external-site"), allow_external_site=True)

    with pytest.raises(ValueError, match="outside data/reports"):
        validate_site_dir_path(Path("public-site"))

    with pytest.raises(ValueError, match="directory path"):
        validate_site_dir_path(Path("data/reports/site.html"))
