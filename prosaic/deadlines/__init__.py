"""Statutory date computation.

This package is pure: no I/O, no network, no language model, no imports
outside the standard library. Holiday calendars arrive as data; every
function maps input dates to output dates deterministically.
"""

from prosaic.deadlines.types import CalendarDays, CourtDays, ServiceMethod

__all__ = ["CalendarDays", "CourtDays", "ServiceMethod"]
