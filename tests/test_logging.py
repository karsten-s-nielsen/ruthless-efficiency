import logging

from ruthless._logging import get_logger


def test_logger_namespaced_and_no_handlers():
    log = get_logger("strategy")
    assert log.name == "ruthless.strategy"
    assert logging.getLogger("ruthless").handlers == []  # library never configures root/handlers


def test_logger_emits(caplog):
    log = get_logger("strategy")
    with caplog.at_level(logging.INFO, logger="ruthless.strategy"):
        log.info("trial_start")
    assert any(r.message == "trial_start" for r in caplog.records)
