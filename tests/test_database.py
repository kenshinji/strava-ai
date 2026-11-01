from app.db.database import _with_psycopg2, engine


class TestWithPsycopg2:
    """SQLAlchemy 2.1 defaults the bare "postgresql://" scheme to psycopg (v3),
    which we don't ship. The driver must stay explicit."""

    def test_bare_scheme_gets_driver(self):
        assert _with_psycopg2("postgresql://user:pw@host:5432/db") == (
            "postgresql+psycopg2://user:pw@host:5432/db"
        )

    def test_explicit_driver_is_left_alone(self):
        url = "postgresql+psycopg2://user:pw@host:5432/db"
        assert _with_psycopg2(url) == url

    def test_other_driver_is_left_alone(self):
        url = "postgresql+asyncpg://user:pw@host:5432/db"
        assert _with_psycopg2(url) == url

    def test_only_the_scheme_is_rewritten(self):
        # A password or dbname containing the scheme text must not be touched.
        assert _with_psycopg2("postgresql://u:postgresql://@host/db") == (
            "postgresql+psycopg2://u:postgresql://@host/db"
        )


class TestEngine:
    def test_engine_uses_psycopg2(self):
        assert engine.dialect.driver == "psycopg2"
