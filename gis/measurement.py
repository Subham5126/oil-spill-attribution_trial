"""Compatibility alias for gis.measurements.

Ensures that both 'from gis.measurements import ...' and 'from gis.measurement import ...'
resolve cleanly without breaking architectural conventions.
"""

from gis.measurements import *
from gis.measurements import __all__
