"""Upgrade 032 on a disposable database. The application database is not migrated.

Downgrade is a no-op. Recovery is restoring the backup taken before upgrade and
restarting the API and workers. This test drops only the database it creates.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.base import Base
from app.models.assessment import AssessmentDecision, AssessmentEvidence, ExternalEffect
from app.models.autonomy import AutonomousRun, AutonomousRunStep, AutopilotSettings

_ADMIN = os.environ.get("M032_ADMIN_URL", "postgresql+psycopg://agrayian:agrayian@127.0.0.1:5435/postgres")
_APP = os.environ.get("M032_APP_URL", "postgresql+psycopg://agrayian:agrayian@127.0.0.1:5435/agrayian")
_NEW_TABLES = ("assessment_evidence", "assessment_decisions", "external_effects")
_RUN_COLUMNS = ("parent_run_id", "business_state", "lease_owner", "lease_until", "paused_at", "cancelled_at")
_STEP_COLUMNS = ("lease_owner", "lease_until", "effect_key", "outcome")


def _redact(value: str) -> str:
    return re.sub(r"postgres(?:ql)?(?:\+\w+)?://\S+", "postgresql://redacted", value)


def _connect(url: str):
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        engine.dispose()
        pytest.fail(f"Disposable PostgreSQL is unavailable ({type(exc).__name__})")
    return engine


def _alembic(url: str, *args: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
        handle.write("ENVIRONMENT=test\n")
        env_file = handle.name
    env = os.environ.copy()
    env["AGRAYIAN_ENV_FILE"] = env_file
    env["DATABASE_URL"] = url
    env["DATABASE_ADMIN_URL"] = url
    env["APP_DB_PASSWORD"] = "agrayian"
    env["ENVIRONMENT"] = "test"
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    os.remove(env_file)
    if completed.returncode != 0:
        detail = _redact((completed.stderr or completed.stdout or "")[-2000:])
        pytest.fail(f"alembic {' '.join(args)} failed: {detail}")


def _column_length(conn, table: str, column: str) -> int | None:
    return conn.execute(
        text(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    ).scalar()


def _insert_required(conn, table: str, overrides: dict) -> None:
    rows = conn.execute(
        text(
            """
            SELECT column_name, is_nullable, column_default, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table},
    ).mappings()
    values: dict[str, object] = {}
    for row in rows:
        name = str(row["column_name"])
        if name in overrides:
            values[name] = overrides[name]
            continue
        if row["column_default"] is not None or row["is_nullable"] == "YES":
            continue
        kind = str(row["data_type"])
        if kind == "boolean":
            values[name] = False
        elif kind in {"integer", "bigint", "numeric", "smallint"}:
            values[name] = 0
        elif "timestamp" in kind:
            values[name] = datetime.now(UTC)
        elif kind == "uuid":
            values[name] = uuid4()
        else:
            values[name] = "completed" if name == "status" else ""
    columns = ", ".join(values)
    binds = ", ".join(f":{name}" for name in values)
    conn.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({binds})"), values)


def _model_columns(model: type) -> set[str]:
    return {column.name for column in model.__table__.columns}


def _db_columns(conn, table: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table},
    )
    return {str(row[0]) for row in rows}


@pytest.mark.postgres
def test_migration_032_upgrades_a_disposable_database_and_downgrade_is_not_a_rollback() -> None:
    admin = _connect(_ADMIN)
    app_version = None
    app_engine = None
    try:
        app_engine = create_engine(_APP)
        with app_engine.connect() as app_conn:
            app_version = app_conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except SQLAlchemyError:
        app_version = None
    finally:
        if app_engine is not None:
            app_engine.dispose()

    name = f"m032_{uuid4().hex[:12]}"
    url = _ADMIN.rsplit("/", 1)[0] + f"/{name}"
    disposable = None
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        _alembic(url, "upgrade", "031")
        disposable = _connect(url)
        with disposable.connect() as conn:
            before_length = _column_length(conn, "autonomous_runs", "status")
            assert before_length is not None
            tenant_id = uuid4()
            user_id = uuid4()
            run_id = uuid4()
            _insert_required(conn, "tenants", {"id": tenant_id, "name": "Migration tenant", "slug": f"m032-{name}"})
            _insert_required(
                conn,
                "users",
                {
                    "id": user_id,
                    "tenant_id": tenant_id,
                    "email": f"{name}@example.com",
                    "name": "Migration user",
                    "password_hash": "not-a-secret",
                },
            )
            _insert_required(
                conn,
                "autonomous_runs",
                {"id": run_id, "tenant_id": tenant_id, "created_by": user_id, "status": "completed", "workflow": "lead_intake"},
            )
            _insert_required(conn, "autopilot_settings", {"id": uuid4(), "tenant_id": tenant_id, "created_by": user_id})
            if before_length != 20:
                conn.execute(text("ALTER TABLE autonomous_runs ALTER COLUMN status TYPE varchar(20)"))
        with disposable.connect() as conn:
            with pytest.raises(SQLAlchemyError):
                conn.execute(
                    text("UPDATE autonomous_runs SET status = :status WHERE id = :id"),
                    {"status": "waiting_for_configuration", "id": run_id},
                )
        with disposable.connect() as conn:
            stored = conn.execute(text("SELECT status FROM autonomous_runs WHERE id = :id"), {"id": run_id}).scalar()
            assert stored == "completed"

        _alembic(url, "upgrade", "032")
        with disposable.connect() as conn:
            assert _column_length(conn, "autonomous_runs", "status") == 40
            conn.execute(
                text("UPDATE autonomous_runs SET status = :status WHERE id = :id"),
                {"status": "waiting_for_configuration", "id": run_id},
            )
            widened = conn.execute(text("SELECT status, business_state FROM autonomous_runs WHERE id = :id"), {"id": run_id}).one()
            assert widened.status == "waiting_for_configuration"
            assert (widened.business_state or "") == ""
            for column in _RUN_COLUMNS:
                assert column in _db_columns(conn, "autonomous_runs")
            for column in _STEP_COLUMNS:
                assert column in _db_columns(conn, "autonomous_run_steps")
            assert "sales_rules_json" in _db_columns(conn, "autopilot_settings")
            for table, model in (
                ("assessment_evidence", AssessmentEvidence),
                ("assessment_decisions", AssessmentDecision),
                ("external_effects", ExternalEffect),
                ("autonomous_runs", AutonomousRun),
                ("autonomous_run_steps", AutonomousRunStep),
                ("autopilot_settings", AutopilotSettings),
            ):
                assert _model_columns(model) == _db_columns(conn, table)
            constraints = {
                str(row[0])
                for row in conn.execute(
                    text("SELECT conname FROM pg_constraint WHERE conname IN ('uq_assessment_evidence', 'uq_external_effect_key')")
                )
            }
            assert constraints == {"uq_assessment_evidence", "uq_external_effect_key"}
            for table in _NEW_TABLES:
                grants = {
                    str(row[0])
                    for row in conn.execute(
                        text(
                            """
                            SELECT privilege_type
                            FROM information_schema.role_table_grants
                            WHERE grantee = 'agrayian_app' AND table_name = :table
                            """
                        ),
                        {"table": table},
                    )
                }
                assert {"SELECT", "INSERT", "UPDATE", "DELETE"} <= grants
                security = conn.execute(
                    text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :table"),
                    {"table": table},
                ).one()
                assert security.relrowsecurity is True
                assert security.relforcerowsecurity is True
            other_tenant = uuid4()
            _insert_required(conn, "tenants", {"id": other_tenant, "name": "Other tenant", "slug": f"other-{name}"})
            _insert_required(
                conn,
                "assessment_evidence",
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "person_id": "person-a",
                    "kind": "reply",
                    "source": "email",
                    "content_hash": "a" * 64,
                    "observed_at": datetime.now(UTC),
                },
            )
            _insert_required(
                conn,
                "assessment_evidence",
                {
                    "id": uuid4(),
                    "tenant_id": other_tenant,
                    "person_id": "person-b",
                    "kind": "reply",
                    "source": "email",
                    "content_hash": "b" * 64,
                    "observed_at": datetime.now(UTC),
                },
            )
        rls = create_engine(url)
        try:
            with rls.connect() as conn:
                conn.execute(text("SET ROLE agrayian_app"))
                conn.execute(text("SELECT set_config('app.current_tenant_id', :tenant, true)"), {"tenant": str(tenant_id)})
                visible = conn.execute(text("SELECT person_id FROM assessment_evidence ORDER BY person_id")).scalars().all()
                assert visible == ["person-a"]
                conn.rollback()
        finally:
            rls.dispose()

        _alembic(url, "downgrade", "-1")
        with disposable.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version == "031"
            assert "assessment_evidence" in {
                str(row[0])
                for row in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            }
            assert _column_length(conn, "autonomous_runs", "status") == 40
            kept = conn.execute(text("SELECT status FROM autonomous_runs WHERE id = :id"), {"id": run_id}).scalar()
            assert kept == "waiting_for_configuration"
    finally:
        if disposable is not None:
            disposable.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
        if app_version is not None:
            check = create_engine(_APP)
            try:
                with check.connect() as conn:
                    after = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                assert after == app_version
            finally:
                check.dispose()


def test_documented_models_match_the_metadata_contract() -> None:
    assert Base.metadata.tables["autonomous_runs"].c.status.type.length == 40
    assert Base.metadata.tables["external_effects"].c.outcome.type.length == 32
    assert "uq_assessment_evidence" in {item.name for item in AssessmentEvidence.__table__.constraints}
