from typing import Optional, Tuple, Any

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, Integer, BigInteger, LargeBinary, orm
import sqlalchemy as sql

from .orm import AlchemySession
from .core import AlchemyCoreSession
from .core_mysql import AlchemyMySQLCoreSession
from .core_postgres import AlchemyPostgresCoreSession

LATEST_VERSION = 2


class AlchemySessionContainer:
    def __init__(self, engine=None, session: orm.Session = None, table_prefix: str = "",
                 table_base: Optional[declarative_base] = None, manage_tables: bool = True) -> None:
        if isinstance(engine, str):
            engine = sql.create_engine(engine)

        self.db_engine = engine
        if not session:
            db_factory = orm.sessionmaker(bind=self.db_engine)
            self.db = orm.scoping.scoped_session(db_factory)
        else:
            self.db = session

        table_base = table_base or declarative_base()
        (self.Version, self.Session, self.Entity,
         self.SentFile, self.UpdateState) = self.create_table_classes(self.db, table_prefix,
                                                                      table_base)
        self.alchemy_session_class = AlchemySession

        if manage_tables:
            table_base.metadata.bind = self.db_engine
            if not self.db_engine.dialect.has_table(self.db_engine,
                                                    self.Version.__tablename__):
                table_base.metadata.create_all()
                self.db.add(self.Version(version=LATEST_VERSION))
                self.db.commit()
            else:
                self.check_and_upgrade_database()

    @property
    def core_mode(self) -> bool:
        return self.alchemy_session_class != AlchemySession

    @core_mode.setter
    def core_mode(self, val: bool) -> None:
        if val:
            if self.db_engine.dialect.name == "mysql":
                self.alchemy_session_class = AlchemyMySQLCoreSession
            elif self.db_engine.dialect.name == "postgres":
                self.alchemy_session_class = AlchemyPostgresCoreSession
            else:
                self.alchemy_session_class = AlchemyCoreSession
        else:
            self.alchemy_session_class = AlchemySession

    @staticmethod
    def create_table_classes(db, prefix: str, base: declarative_base
                             ) -> Tuple[Any, Any, Any, Any, Any]:
        class Version(base):
            query = db.query_property()
            __tablename__ = "{prefix}version".format(prefix=prefix)
            version = Column(Integer, primary_key=True)

            def __str__(self):
                return "Version('{}')".format(self.version)

        class Session(base):
            query = db.query_property()
            __tablename__ = '{prefix}sessions'.format(prefix=prefix)

            session_id = Column(String(255), primary_key=True)
            dc_id = Column(Integer, primary_key=True)
            server_address = Column(String(255))
            port = Column(Integer)
            auth_key = Column(LargeBinary)

            def __str__(self):
                return "Session('{}', {}, '{}', {}, {})".format(self.session_id, self.dc_id,
                                                                self.server_address, self.port,
                                                                self.auth_key)

        class Entity(base):
            query = db.query_property()
            __tablename__ = '{prefix}entities'.format(prefix=prefix)

            session_id = Column(String(255), primary_key=True)
            id = Column(BigInteger, primary_key=True)
            hash = Column(BigInteger, nullable=False)
            username = Column(String(32))
            phone = Column(BigInteger)
            name = Column(String(255))

            def __str__(self):
                return "Entity('{}', {}, {}, '{}', '{}', '{}')".format(self.session_id, self.id,
                                                                       self.hash, self.username,
                                                                       self.phone, self.name)

        class SentFile(base):
            query = db.query_property()
            __tablename__ = '{prefix}sent_files'.format(prefix=prefix)

            session_id = Column(String(255), primary_key=True)
            md5_digest = Column(LargeBinary, primary_key=True)
            file_size = Column(Integer, primary_key=True)
            type = Column(Integer, primary_key=True)
            id = Column(BigInteger)
            hash = Column(BigInteger)

            def __str__(self):
                return "SentFile('{}', {}, {}, {}, {}, {})".format(self.session_id,
                                                                   self.md5_digest, self.file_size,
                                                                   self.type, self.id, self.hash)

        class UpdateState(base):
            query = db.query_property()
            __tablename__ = "{prefix}update_state".format(prefix=prefix)

            session_id = Column(String(255), primary_key=True)
            entity_id = Column(BigInteger, primary_key=True)
            pts = Column(BigInteger)
            qts = Column(BigInteger)
            date = Column(BigInteger)
            seq = Column(BigInteger)
            unread_count = Column(Integer)

        return Version, Session, Entity, SentFile, UpdateState

    def _add_column(self, table: Any, column: Column) -> None:
        column_name = column.compile(dialect=self.db_engine.dialect)
        column_type = column.type.compile(self.db_engine.dialect)
        self.db_engine.execute("ALTER TABLE {} ADD COLUMN {} {}".format(
            table.__tablename__, column_name, column_type))

    def check_and_upgrade_database(self) -> None:
        row = self.Version.query.all()
        version = row[0].version if row else 1
        if version == LATEST_VERSION:
            return

        self.Version.query.delete()

        if version == 1:
            self.UpdateState.__table__.create(self.db_engine)
            version = 3
        elif version == 2:
            self._add_column(self.UpdateState, Column(type=Integer, name="unread_count"))

        self.db.add(self.Version(version=version))
        self.db.commit()

    def new_session(self, session_id: str) -> 'AlchemySession':
        return self.alchemy_session_class(self, session_id)

    def list_sessions(self):
        return

    def save(self) -> None:
        self.db.commit()
