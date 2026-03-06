
import logging

def get_logger(name):

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    logger.addHandler(handler)

    return logger
