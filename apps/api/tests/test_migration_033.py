"""Upgrade 033 on a disposable database. The application database is not migrated.

Downgrade is a no-op. Recovery is restoring the backup taken before upgrade and
restarting the API and workers. This test drops only the database it creates.
"""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from tests.test_migration_032 import _ADMIN, _APP, _alembic, _connect, _insert_required

_TABLES = ("operating_plans", "creative_versions")


@pytest.mark.postgres
def test_migration_033_enforces_tenant_isolation_on_a_disposable_database() -> None:
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

    name = f"m033_{uuid4().hex[:12]}"
    url = _ADMIN.rsplit("/", 1)[0] + f"/{name}"
    disposable = None
    tenant_id = uuid4()
    other_tenant = uuid4()
    plan_id = uuid4()
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        _alembic(url, "upgrade", "033")
        disposable = _connect(url)
        with disposable.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version == "033"
            for table in _TABLES:
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
            _insert_required(conn, "tenants", {"id": tenant_id, "name": "Plan tenant", "slug": f"m033-{name}"})
            _insert_required(conn, "tenants", {"id": other_tenant, "name": "Other plan tenant", "slug": f"other-{name}"})
            _insert_required(
                conn,
                "operating_plans",
                {"id": plan_id, "tenant_id": tenant_id, "channel": "linkedin", "status": "running", "audience": "Ops leaders"},
            )
            _insert_required(
                conn,
                "operating_plans",
                {"id": uuid4(), "tenant_id": other_tenant, "channel": "linkedin", "status": "running", "audience": "Hidden"},
            )
            _insert_required(
                conn,
                "creative_versions",
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "plan_id": plan_id,
                    "channel": "linkedin",
                    "version_number": 1,
                    "content_hash": "a" * 64,
                    "status": "authorized",
                    "body": "Authorized copy stays immutable.",
                },
            )
        rls = create_engine(url)
        try:
            with rls.connect() as conn:
                conn.execute(text("SET ROLE agrayian_app"))
                conn.execute(text("SELECT set_config('app.current_tenant_id', :tenant, true)"), {"tenant": str(tenant_id)})
                visible = conn.execute(text("SELECT audience FROM operating_plans ORDER BY audience")).scalars().all()
                assert visible == ["Ops leaders"]
                versions = conn.execute(text("SELECT status FROM creative_versions")).scalars().all()
                assert versions == ["authorized"]
                conn.rollback()
        finally:
            rls.dispose()

        _alembic(url, "downgrade", "-1")
        with disposable.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version == "032"
            tables = {
                str(row[0]) for row in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            }
            assert {"operating_plans", "creative_versions"} <= tables
            kept = conn.execute(text("SELECT audience FROM operating_plans WHERE id = :id"), {"id": plan_id}).scalar()
            assert kept == "Ops leaders"
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
