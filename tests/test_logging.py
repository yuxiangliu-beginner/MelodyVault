import logging
from melodyvault.logging_setup import configure_logging, close_logging


def test_log_redaction_rotation_and_no_duplicate_handlers(tmp_path):
    logger = configure_logging(tmp_path)
    logger = configure_logging(tmp_path)
    try:
        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        assert handler.maxBytes > 0 and handler.backupCount == 3
        logger.info('access_token=secret-a refresh_token="secret-b" Authorization: Bearer secret-c')
        logger.info('{"client_secret": "secret-d", "api_key": "secret-e"}')
        try:
            raise ValueError("password=secret-f")
        except ValueError:
            logger.exception("Example failure")
        handler.flush()
        text = (tmp_path / "melodyvault.log").read_text(encoding="utf-8")
        for value in ("secret-a", "secret-b", "secret-c", "secret-d", "secret-e", "secret-f"):
            assert value not in text
        assert "[REDACTED]" in text
        assert "Example failure" in text
    finally:
        close_logging()
    assert not logging.getLogger("melodyvault").handlers
