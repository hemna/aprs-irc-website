from pathlib import Path

home = str(Path.home())
DEFAULT_CONFIG_DIR = "{}/.config/aprsd_repeat/".format(home)
DEFAULT_CONFIG_FILE = "{}/.config/aprsd_repeat/aprsd_repeat.conf".format(home)


def hsl_to_rgb(hsl):
    """Convert hsl colorspace values to RGB."""
    # Convert hsl to 0-1 ranges.
    h = hsl[0] / 359.
    s = hsl[1] / 100.
    lumen = hsl[2] / 100.
    hsl = (h, s, lumen)
    # returns numbers between 0 and 1
    tmp = colorsys.hls_to_rgb(h, s, lumen)
    # convert to 0 to 255
    r = int(round(tmp[0] * 255))
    g = int(round(tmp[1] * 255))
    b = int(round(tmp[2] * 255))
    return (r, g, b)


# ping an rgb tuple based on percent.
# clip shifts the color space towards the
# clip percentage
def pick_color(percent, clip, saturation, start, end):
    """Pick an rgb color based on % value.

    Clip can shift the color gradient towards the clip value.
    Valid clip values are 0-100.
    Saturation (0-100) is how bright the range of colors are.
    start = start hue value.  (0 = red, 120 = green)
    end = end hue value.  (0 = red, 120 = green)
    """
    a = 0 if (percent <= clip) else (((percent - clip) / (100 - clip)))
    b = abs(end - start) * a
    c = (start + b) if (end > start) else (start - b)

    h = int(round(c))
    s = int(saturation)
    return hsl_to_rgb((h, 50, s))


def alert_percent_color(percent, start=0, end=120):
    """Return rgb color based on % value.

    This is a wrapper function for pick_color, with clipping
    set to 0, and saturation set to 100%.

    By default the colors range from Red at 0% to
    Green at 100%.   If you want the colors to invert
    then set start=120, end=0.  The start and end values
    are hue.  Green is 120 hue.
    """
    return pick_color(percent, 0, 100, start, end)


def rgb_from_name(name):
    """Create an rgb tuple from a string."""
    hash = 0
    for char in name:
        hash = ord(char) + ((hash << 5) - hash)
    red = hash & 255
    green = (hash >> 8) & 255
    blue = (hash >> 16) & 255
    return red, green, blue
