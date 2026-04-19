"""Unit tests for the number platform.

The variable-speed pump speed control was moved from NumberEntity (number.py)
to SelectEntity (select.py / KlereoPumpSpeedSelect) so that each discrete
speed level is presented as a named option.  See test_select.py for full
coverage of the pump speed entity.

This file is kept as a placeholder for future number entities (e.g. regulation
setpoints via SetParam.php — ConsigneEau, ConsignePH, ConsigneRedox, ConsigneChlore).
"""


def test_number_platform_placeholder():
    """Placeholder — no number entities registered yet."""
    pass
