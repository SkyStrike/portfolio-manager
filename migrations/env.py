import os
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override DB URL from the PORTFOLIO_DB_FILE environment variable,
# consistent with how core/database.py resolves the database path.
DB_FILE = os.getenv("PORTFOLIO_DB_FILE", "data/portfolio.db")
DB_URL = f"sqlite:///{DB_FILE}"

# Override the config sqlalchemy.url with the resolved path
config.set_main_option("sqlalchemy.url", DB_URL)

# target_metadata is set to None since we use raw SQL in migrations
# (no SQLAlchemy ORM models). To enable autogenerate, you would
# import your models' Base.metadata here.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.
    """
    context.configure(
        url=DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a
    connection with the context.
    """
    connectable = create_engine(
        DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
