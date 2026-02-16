import structlog


def get_agent_commons_logger(name):
    """This will add a `agent_commons` prefix to logger for easy configuration."""

    return structlog.get_logger(
        f"agent_commons.{name}",
        project="agent_commons"
    )
