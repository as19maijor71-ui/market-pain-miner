from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from app.cli import run_classify, run_import, run_report, validate_report_path


FIXTURE = Path(__file__).parent / "fixtures" / "telegram_solutions_result.json"


@contextmanager
def temporary_db_path() -> Iterator[Path]:
    db_path = Path(__file__).parent / f"_tmp_report_{uuid4().hex}.sqlite"
    try:
        yield db_path
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{db_path}{suffix}")
            if candidate.exists():
                candidate.unlink()


@contextmanager
def temporary_report_path() -> Iterator[Path]:
    report_path = Path(__file__).parent / f"_tmp_report_{uuid4().hex}.html"
    try:
        yield report_path
    finally:
        if report_path.exists():
            report_path.unlink()


def test_html_report_is_generated_and_privacy_safe_by_default(capsys) -> None:
    with temporary_db_path() as db_path, temporary_report_path() as report_path:
        run_import(FIXTURE, db_path)
        run_classify(db_path)
        capsys.readouterr()

        result = run_report(db_path, report_path, limit=10)
        output = capsys.readouterr().out

        html = report_path.read_text(encoding="utf-8")

    assert "HTML report generated" in output
    assert result["path"].endswith(".html")
    assert "<h1>Отчет по Telegram-чату WB/Ozon</h1>" in html
    assert "Сводка" in html
    assert "Кластеры Болей И Вопросов" in html
    assert "Решения И Конкуренты" in html
    assert "Гипотезы" in html
    assert "Ручная Проверка" in html
    assert "chat1:1" in html

    assert "Synthetic Solutions Fixture" not in html
    assert "synthetic_participant" not in html
    assert "3000000000" not in html
    assert "https://sellerstock.test" not in html
    assert "sellerstock.test" not in html
    assert "@StockPilot" not in html
    assert "Не могу свести" not in html
    assert "Рекомендую бот" not in html


def test_report_path_rejects_trackable_html_by_default() -> None:
    validate_report_path(Path("tests/_tmp_safe.html"))
    validate_report_path(Path("external-report.html"), allow_external_report=True)

    with pytest.raises(ValueError, match="outside data/reports"):
        validate_report_path(Path("public-report.html"))

    with pytest.raises(ValueError, match="must end with"):
        validate_report_path(Path("data/reports/report.txt"))
