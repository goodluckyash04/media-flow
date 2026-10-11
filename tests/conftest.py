"""Pytest configuration and compatibility patches."""

import sys
from django.template.context import BaseContext


# Python 3.14 compatibility patch for Django 5.1 BaseContext.__copy__
if sys.version_info >= (3, 14):
    def _safe_basecontext_copy(self):
        cls = self.__class__
        dup = cls.__new__(cls)
        dup.dicts = self.dicts[:]
        return dup

    BaseContext.__copy__ = _safe_basecontext_copy
