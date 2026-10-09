"""Every RTT colour the map can draw meets 3:1 against land and sea (WCAG 2.1, 1.4.11).

Over every palette, both themes and every warm-to-hot blend theme.step_color
can produce, so a colour changed later that drops below 3:1 fails here.
"""
import pytest

pytest.importorskip("PySide6")

from routemap.gui import theme  # noqa: E402


def _lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("base", [theme.LIGHT, theme.DARK], ids=["light", "dark"])
@pytest.mark.parametrize("name", theme.RTT_PALETTES)
def test_every_rtt_colour_meets_3_to_1(base, name):
    pal = theme.with_rtt(base, name)
    colours = [("quiet", pal.route_quiet)] + [
        (f"step {i / 20:.2f}", theme.step_color(pal, "warm", i / 20)) for i in range(21)]
    for label, colour in colours:
        for ground_name, ground in (("land", pal.land), ("ocean", pal.ocean)):
            assert contrast(colour, ground) >= 3.0, (name, label, colour.name(), ground_name,
                                                     round(contrast(colour, ground), 2))
