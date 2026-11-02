import unittest
from sqlalchemy import create_engine, text
from schema_readiness import schema_ready,required_revision

class SchemaReadinessTest(unittest.TestCase):
    def test_unmigrated_database_refuses_release(self):
        engine=create_engine('sqlite://')
        self.assertFalse(schema_ready(engine))
        with engine.begin() as c:
            c.execute(text('CREATE TABLE alembic_version(version_num TEXT)'))
            c.execute(text("INSERT INTO alembic_version VALUES ('c4527f019a21')"))
        self.assertFalse(schema_ready(engine))
        engine.dispose()

    def test_stamped_but_missing_operational_tables_refuses_release(self):
        engine=create_engine('sqlite://')
        with engine.begin() as c:
            c.execute(text('CREATE TABLE alembic_version(version_num TEXT)'))
            c.execute(text('INSERT INTO alembic_version VALUES (:revision)'),{'revision':required_revision()})
        self.assertFalse(schema_ready(engine))
        engine.dispose()
