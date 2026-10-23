"""Upgrade 034 on a disposable database. The application database is not migrated.

Downgrade is a no-op. Recovery is restoring the backup taken before upgrade and
restarting the API and workers. This test drops only the database it creates.
"""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from tests.test_migration_032 import _ADMIN, _APP, _alembic, _connect, _insert_required


@pytest.mark.postgres
def test_migration_034_enforces_tenant_isolation_on_a_disposable_database() -> None:
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

    name = f"m034_{uuid4().hex[:12]}"
    url = _ADMIN.rsplit("/", 1)[0] + f"/{name}"
    disposable = None
    tenant_id = uuid4()
    other_tenant = uuid4()
    scope_id = uuid4()
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        _alembic(url, "upgrade", "head")
        disposable = _connect(url)
        with disposable.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version == "034"
            columns = {
                (str(row.table_name), str(row.column_name))
                for row in conn.execute(
                    text(
                        """
                        SELECT table_name, column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND (
                            (table_name = 'operating_plans' AND column_name = 'context_snapshot')
                            OR (table_name = 'email_messages' AND column_name = 'header_json')
                          )
                        """
                    )
                )
            }
            assert columns == {("operating_plans", "context_snapshot"), ("email_messages", "header_json")}
            grants = {
                str(row[0])
                for row in conn.execute(
                    text(
                        """
                        SELECT privilege_type
                        FROM information_schema.role_table_grants
                        WHERE grantee = 'agrayian_app' AND table_name = 'demo_scopes'
                        """
                    )
                )
            }
            assert {"SELECT", "INSERT", "UPDATE", "DELETE"} <= grants
            security = conn.execute(
                text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'demo_scopes'")
            ).one()
            assert security.relrowsecurity is True
            assert security.relforcerowsecurity is True
            _insert_required(conn, "tenants", {"id": tenant_id, "name": "Demo tenant", "slug": f"m034-{name}"})
            _insert_required(conn, "tenants", {"id": other_tenant, "name": "Other demo tenant", "slug": f"other-{name}"})
            _insert_required(
                conn,
                "demo_scopes",
                {
                    "id": scope_id,
                    "tenant_id": tenant_id,
                    "buyer_email": "buyer@example.com",
                    "status": "prepared",
                    "notes": "Visible scope",
                },
            )
            _insert_required(
                conn,
                "demo_scopes",
                {
                    "id": uuid4(),
                    "tenant_id": other_tenant,
                    "buyer_email": "hidden@example.com",
                    "status": "prepared",
                    "notes": "Hidden scope",
                },
            )
        rls = create_engine(url)
        try:
            with rls.connect() as conn:
                conn.execute(text("SET ROLE agrayian_app"))
                conn.execute(text("SELECT set_config('app.current_tenant_id', :tenant, true)"), {"tenant": str(tenant_id)})
                visible = conn.execute(text("SELECT notes FROM demo_scopes ORDER BY notes")).scalars().all()
                assert visible == ["Visible scope"]
                conn.rollback()
        finally:
            rls.dispose()

        _alembic(url, "downgrade", "-1")
        with disposable.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version == "033"
            kept = conn.execute(text("SELECT notes FROM demo_scopes WHERE id = :id"), {"id": scope_id}).scalar()
            assert kept == "Visible scope"
            snapshot = conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'operating_plans' AND column_name = 'context_snapshot'
                    """
                )
            ).scalar()
            assert snapshot == "context_snapshot"
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
