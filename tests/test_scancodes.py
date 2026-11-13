from moukey.backends.scancodes import CODES, NAMES, evdev_code, name_for_evdev


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


def test_linux_codes():
    assert evdev_code("a") == 30  # KEY_A
    assert evdev_code("esc") == 1
    assert evdev_code("f12") == 88
    assert evdev_code("up") == 103
    assert evdev_code("delete") == 111
    assert evdev_code("meta_l") == 125
    assert evdev_code("intl_ro") == 89  # the /? key on abnt2
    assert evdev_code("nao-existe") is None


def test_every_key_has_a_linux_code():
    assert all(evdev_code(name) for name in CODES)


def test_linux_codes_go_both_ways():
    for name in CODES:
        assert name_for_evdev(evdev_code(name)) == name
    assert name_for_evdev(9999) is None
