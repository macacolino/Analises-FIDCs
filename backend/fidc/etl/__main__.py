"""Uso: python -m fidc.etl [--sem-download]"""
import logging
import sys

from .pipeline import run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
print(run(download="--sem-download" not in sys.argv))
