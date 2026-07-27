"""Compatibility imports for focused TLB RAG helper tests.

The production implementations live in :mod:`.core`; keeping this module free
of import-time assertions makes it safe for test runners and package users.
"""

from .core import _dict_to_tlb_result, _extract_json

__all__ = ["_dict_to_tlb_result", "_extract_json"]
