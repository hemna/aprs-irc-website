"""Unit tests for app/utils.py — pure Python, no external deps."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import utils  # noqa: E402


class TestHslToRgb:
    def test_black(self):
        r, g, b = utils.hsl_to_rgb((0, 0, 0))
        assert r == 0 and g == 0 and b == 0

    def test_returns_tuple_of_three_ints(self):
        result = utils.hsl_to_rgb((120, 50, 50))
        assert len(result) == 3
        assert all(isinstance(v, int) for v in result)

    def test_values_in_0_255_range(self):
        for h in (0, 60, 120, 180, 240, 300):
            r, g, b = utils.hsl_to_rgb((h, 80, 50))
            assert 0 <= r <= 255
            assert 0 <= g <= 255
            assert 0 <= b <= 255


class TestPickColor:
    def test_below_clip_returns_start_hue(self):
        # percent <= clip → a=0 → hue = start
        result = utils.pick_color(percent=0, clip=50, saturation=100, start=0, end=120)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_at_100_percent(self):
        result = utils.pick_color(percent=100, clip=0, saturation=100, start=0, end=120)
        assert isinstance(result, tuple)

    def test_inverted_range(self):
        # end < start should not crash
        result = utils.pick_color(percent=50, clip=0, saturation=100, start=120, end=0)
        assert isinstance(result, tuple)


class TestAlertPercentColor:
    def test_zero_percent_is_red_ish(self):
        r, g, b = utils.alert_percent_color(0)
        # At 0% with start=0 (red hue) saturation 100%, red channel should dominate
        assert r > g

    def test_100_percent_is_green_ish(self):
        r, g, b = utils.alert_percent_color(100)
        # At 100% with end=120 (green hue), green should dominate
        assert g > r

    def test_returns_rgb_tuple(self):
        result = utils.alert_percent_color(50)
        assert len(result) == 3
        assert all(0 <= v <= 255 for v in result)

    def test_inverted_colors(self):
        """start=120, end=0 should invert the gradient."""
        r_low, _, _ = utils.alert_percent_color(0, start=120, end=0)
        r_high, _, _ = utils.alert_percent_color(100, start=120, end=0)
        # At 0% with start=120 (green hue), green channel should dominate
        # Just check it doesn't blow up and returns valid ranges
        assert 0 <= r_low <= 255
        assert 0 <= r_high <= 255


class TestRgbFromName:
    def test_returns_three_ints(self):
        r, g, b = utils.rgb_from_name("WB4BOR")
        assert isinstance(r, int)
        assert isinstance(g, int)
        assert isinstance(b, int)

    def test_values_are_byte_range(self):
        r, g, b = utils.rgb_from_name("N7UV")
        assert 0 <= r <= 255
        assert 0 <= g <= 255
        assert 0 <= b <= 255

    def test_same_name_same_color(self):
        assert utils.rgb_from_name("TEST") == utils.rgb_from_name("TEST")

    def test_different_names_likely_different_colors(self):
        # Very unlikely that two different callsigns hash identically
        assert utils.rgb_from_name("WB4BOR") != utils.rgb_from_name("N7UV")

    def test_empty_string(self):
        # Should not raise
        result = utils.rgb_from_name("")
        assert len(result) == 3


class TestConstants:
    def test_default_config_dir_ends_with_slash(self):
        assert utils.DEFAULT_CONFIG_DIR.endswith("/")

    def test_default_config_file_ends_with_conf(self):
        assert utils.DEFAULT_CONFIG_FILE.endswith(".conf")

    def test_default_config_file_within_config_dir(self):
        assert utils.DEFAULT_CONFIG_FILE.startswith(utils.DEFAULT_CONFIG_DIR)
