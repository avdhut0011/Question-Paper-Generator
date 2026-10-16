from logging.config import fileConfig
from alembic import context
from flask import current_app

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
database = current_app.extensions['migrate'].db
target_metadata = database.metadata


def run_migrations_offline():
    context.configure(url=database.engine.url.render_as_string(hide_password=False), target_metadata=target_metadata,
                      literal_binds=True, compare_type=True, dialect_opts={'paramstyle': 'named'})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with database.engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
