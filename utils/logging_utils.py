#!/usr/bin/env python3
"""Fonctions de log avec couleurs pour le terminal."""

import logging


class Colors:
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[1;31m"
    BLUE = "\033[1;34m"
    CYAN = "\033[1;36m"
    MAGENTA = "\033[1;35m"
    WHITE = "\033[1;37m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class Logger:
    def __init__(self, name="FedoraForgeKDE", log_file=None):
        self.name = name
        self.log_file = log_file
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            logging.basicConfig(
                filename=str(log_file),
                level=logging.INFO,
                format="%(asctime)s [%(levelname)s] %(message)s",
            )

    def info(self, msg):
        print(f"{Colors.BLUE}[INFO]{Colors.RESET} {msg}")
        if self.log_file:
            logging.info(msg)

    def success(self, msg):
        print(f"{Colors.GREEN}[OK]{Colors.RESET} {msg}")
        if self.log_file:
            logging.info(msg)

    def warn(self, msg):
        print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {msg}")
        if self.log_file:
            logging.warning(msg)

    def error(self, msg):
        print(f"{Colors.RED}[ERROR]{Colors.RESET} {msg}")
        if self.log_file:
            logging.error(msg)

    def debug(self, msg):
        print(f"{Colors.CYAN}[DEBUG]{Colors.RESET} {msg}")
        if self.log_file:
            logging.debug(msg)

    def step(self, msg):
        print(f"{Colors.BOLD}-> {msg}{Colors.RESET}")
        if self.log_file:
            logging.info(f"-> {msg}")

    def header(self, msg):
        separator = "=" * len(msg)
        print(f"\n{Colors.BOLD}{separator}")
        print(msg)
        print(f"{separator}{Colors.RESET}\n")
        if self.log_file:
            logging.info(f"\n{'='*60}\n{msg}\n{'='*60}")


_default_logger = Logger()

def info(msg):       _default_logger.info(msg)
def success(msg):    _default_logger.success(msg)
def warn(msg):       _default_logger.warn(msg)
def error(msg):      _default_logger.error(msg)
def debug(msg):      _default_logger.debug(msg)
def step(msg):       _default_logger.step(msg)
def header(msg):     _default_logger.header(msg)

def set_log_file(log_file):
    global _default_logger
    _default_logger = Logger(log_file=log_file)

# Alias
log_info = info
log_success = success
log_warn = warn
log_error = error
log_debug = debug
log_step = step
log_header = header
