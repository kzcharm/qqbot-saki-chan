"""SQLite migrations run on the connection supplied by the bot."""
from alembic import context


def include_object(obj, name, type_, reflected, compare_to):
    # This migration history owns user preferences only.
    return type_ != "table" or name in {"qqbot_users", "bot_platform_preferences"}


context.configure(
    connection=context.config.attributes["connection"],
    target_metadata=context.config.attributes.get("target_metadata"),
    render_as_batch=True,
    include_object=include_object,
)
with context.begin_transaction():
    context.run_migrations()
