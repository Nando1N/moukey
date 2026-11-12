from moukey.backends.scancodes import CODES, NAMES


def test_names_are_unique():
    assert len(CODES) == len(NAMES)


def test_common_keys():
    assert CODES["a"] == 0x1E
    assert CODES["z"] == 0x2C
    assert CODES["1"] == 0x02
    assert CODES["0"] == 0x0B
    assert CODES["f1"] == 0x3B
    assert CODES["f12"] == 0x58
    assert CODES["kp_0"] == 0x52
    assert CODES["delete"] == 0xE053


def test_has_what_a_shortcut_needs():
    for name in ("ctrl_l", "shift_l", "alt_l", "meta_l", "c", "v", "tab", "esc"):
        assert name in CODES
