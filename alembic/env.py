from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

import sys
import os
# Add project root to path to find app module
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.base_class import Base
from app.db.models.document import Document # Import your models here
# from app.db.models.user import User # Add user model later
# Import config if loading URL from env
# from app.core.config import settings

from app.core.config import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
     # --- This block uses the settings import ---
    # Get the Alembic config section
    alembic_config_section = config.get_section(config.config_ini_section)

    # Set the sqlalchemy.url from your Pydantic settings
    # This line now works because 'settings' is imported
    alembic_config_section['sqlalchemy.url'] = str(settings.DATABASE_URL) # Cast to string

    db_url_being_used = alembic_config_section['sqlalchemy.url']
    # Remove debug print to prevent leaking connection info
    # log.info(f"Alembic connecting using URL: {db_url_being_used}") # Or use logging if configured

    # Create engine using the modified configuration
    connectable = engine_from_config(
        alembic_config_section, # Use updated config
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
