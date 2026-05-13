"""Fetch and cache DSO thumbnail images.

Source priority:
  1. SDSS SkyServer — natural color JPEG, best quality (covers ~dec -10° to +65°, no Milky Way)
  2. Legacy Survey DR10 — natural grz color, good for southern sky
  3. DSS2 Red warm tint — single-band amber fallback, full sky
"""

import io
import logging
from pathlib import Path
from typing import Optional

import requests

from data_dir import DATA_DIR

_log = logging.getLogger(__name__)
_CACHE_DIR = DATA_DIR / "dso_images"
_SDSS_URL   = "https://skyserver.sdss.org/dr17/SkyServerWS/ImgCutout/getjpeg"
_LEGACY_URL = "https://www.legacysurvey.org/viewer/jpeg-cutout"
_SKYVIEW_URL = "https://skyview.gsfc.nasa.gov/current/cgi/runquery.pl"
_WIKI_API   = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_TIMEOUT = 20
_SESSION = requests.Session()

# Wikipedia article titles for objects where the API thumbnail is a real photo.
# Keyed by catalog name; common_name lookups happen at call time.
_WIKI_TITLES: dict[str, str] = {
    "M1":        "Crab_Nebula",
    "M8":        "Lagoon_Nebula",
    "M16":       "Eagle_Nebula",
    "M17":       "Omega_Nebula",
    "M20":       "Trifid_Nebula",
    "M27":       "Dumbbell_Nebula",
    "M42":       "Orion_Nebula",
    "M43":       "Orion_Nebula",  # same region
    "M57":       "Ring_Nebula",
    "M76":       "Little_Dumbbell_Nebula",
    "M97":       "Owl_Nebula",
    "NGC 6888":  "Crescent_Nebula",
    "NGC 7000":  "North_America_Nebula",
    "NGC 2237":  "Rosette_Nebula",
    "NGC 6960":  "Veil_Nebula",
    "NGC 7293":  "Helix_Nebula",
    "NGC 6543":  "Cat%27s_Eye_Nebula",
    "IC 1805":   "Heart_Nebula",
    "IC 1848":   "Soul_Nebula",
    "IC 434":    "Horsehead_Nebula",
}


def _wikipedia_photo(name: str, common_name: str, pixels: int) -> Optional[bytes]:
    """Fetch the Wikipedia lead image for a DSO — usually a real Hubble/pro photo."""
    from PIL import Image
    title = _WIKI_TITLES.get(name)
    if not title:
        # Try matching by common name (e.g. "Eagle Nebula")
        slug = common_name.replace(" ", "_")
        for v in _WIKI_TITLES.values():
            if v.lower() == slug.lower():
                title = v
                break
    if not title:
        return None
    try:
        url = _WIKI_API.format(title=title)
        resp = _SESSION.get(url, timeout=_TIMEOUT,
                            headers={"User-Agent": "AstroAlert/1.0 (astro planning app)"})
        resp.raise_for_status()
        data = resp.json()
        thumb = (data.get("thumbnail") or data.get("originalimage") or {})
        img_url = thumb.get("source")
        if not img_url:
            return None
        img_resp = _SESSION.get(img_url, timeout=_TIMEOUT,
                               headers={"User-Agent": "AstroAlert/1.0 (astro planning app)"})
        img_resp.raise_for_status()
        if "image" not in img_resp.headers.get("content-type", ""):
            return None
        img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
        img = img.resize((pixels, pixels), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        _log.debug("Wikipedia photo failed for %s: %s", name, exc)
    return None


def _ra_to_deg(ra_str: str) -> float:
    parts = ra_str.strip().split(":")
    h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
    return (h + m / 60.0 + s / 3600.0) * 15.0


def _dec_to_deg(dec_str: str) -> float:
    s = dec_str.strip()
    sign = -1.0 if s.startswith("-") else 1.0
    parts = s.lstrip("+-").split(":")
    d, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
    return sign * (d + m / 60.0 + sec / 3600.0)


def _asinh_stretch(img, scale: float = 4.0):
    """Per-channel arcsinh stretch — reveals faint structure without blowing cores."""
    import math
    norm = math.asinh(scale)
    def _s(p):
        return min(255, int(math.asinh(scale * p / 255.0) / norm * 255))
    r, g, b = img.split()
    from PIL import Image as _Img
    return _Img.merge("RGB", [ch.point(_s) for ch in (r, g, b)])


def _sdss_server(ra_deg: float, dec_deg: float,
                 fov_deg: float, pixels: int) -> Optional[bytes]:
    """Fetch a natural-color JPEG from the SDSS SkyServer image cutout service.

    Returns None when outside the SDSS footprint (server returns an error-text
    image that is nearly pitch-black) or when color balance looks wrong.
    """
    from PIL import Image, ImageStat
    fetch_px  = 512                             # fetch at 2× for better downscale quality
    sdss_fov  = min(fov_deg, 0.7)
    scale     = sdss_fov * 3600.0 / fetch_px
    scale     = max(0.1, min(scale, 60.0))
    params = {
        "ra":     f"{ra_deg:.5f}",
        "dec":    f"{dec_deg:.5f}",
        "scale":  f"{scale:.2f}",
        "width":  str(fetch_px),
        "height": str(fetch_px),
    }
    try:
        resp = _SESSION.get(_SDSS_URL, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        if "image" not in resp.headers.get("content-type", ""):
            return None
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        stat = ImageStat.Stat(img)
        mean_all = sum(stat.mean) / 3
        if mean_all < 4.0:
            return None
        r_m, g_m, b_m = stat.mean
        if g_m > r_m * 1.5 or b_m > r_m * 1.5:
            return None
        img = _asinh_stretch(img, scale=4.0)
        img = img.resize((pixels, pixels), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        _log.debug("SDSS SkyServer failed ra=%.4f dec=%.4f: %s", ra_deg, dec_deg, exc)
    return None


def _legacy_survey(ra_deg: float, dec_deg: float,
                   fov_deg: float, pixels: int) -> Optional[bytes]:
    """Fetch a natural-color JPEG from the Legacy Survey DR10 viewer."""
    from PIL import Image, ImageStat, ImageEnhance
    arcsec_per_pixel = fov_deg * 3600.0 / pixels
    params = {
        "ra":       f"{ra_deg:.5f}",
        "dec":      f"{dec_deg:.5f}",
        "size":     str(pixels),
        "layer":    "ls-dr10",
        "pixscale": f"{arcsec_per_pixel:.3f}",
    }
    try:
        resp = _SESSION.get(_LEGACY_URL, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        if "image" not in resp.headers.get("content-type", ""):
            return None
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        stat = ImageStat.Stat(img)
        mean_brightness = sum(stat.mean) / 3
        mean_stddev = sum(stat.stddev) / 3
        if mean_brightness < 4.0 or mean_stddev < 2.0:
            return None
        # Check bright-pixel color balance — grz maps g→B, r→G, z→R so
        # star-forming galaxies come out teal; fall through to DSS for those.
        lum = img.convert("L")
        lum_pixels = sorted(lum.getdata())
        threshold = lum_pixels[int(len(lum_pixels) * 0.85)]
        br = bg = bb = count = 0
        for rp, gp, bp, lp in zip(
            img.split()[0].getdata(), img.split()[1].getdata(),
            img.split()[2].getdata(), lum.getdata()
        ):
            if lp >= threshold:
                br += rp; bg += gp; bb += bp; count += 1
        if count > 0:
            br /= count; bg /= count; bb /= count
        if bb > br * 1.25 or bg > br * 1.35:
            return None
        img = ImageEnhance.Contrast(img).enhance(1.3)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        _log.debug("Legacy Survey failed ra=%.4f dec=%.4f: %s", ra_deg, dec_deg, exc)
    return None


def _skyview_band(ra_deg: float, dec_deg: float, fov_deg: float,
                  pixels: int, survey: str) -> Optional[bytes]:
    params = {
        "Survey":   survey,
        "position": f"{ra_deg:.4f},{dec_deg:.4f}",
        "Size":     f"{fov_deg:.3f}",
        "Pixels":   str(pixels),
        "Return":   "PNG",
        "Sampler":  "NN",
    }
    try:
        resp = _SESSION.get(_SKYVIEW_URL, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        if "image" in resp.headers.get("content-type", ""):
            return resp.content
    except Exception as exc:
        _log.debug("SkyView %s failed: %s", survey, exc)
    return None


def _autolevels(channel):
    lo, hi = channel.getextrema()
    if hi <= lo:
        return channel
    return channel.point(lambda p: int((p - lo) * 255 / (hi - lo)))


def _dss_natural(ra_deg: float, dec_deg: float,
                 fov_deg: float, pixels: int) -> Optional[bytes]:
    """DSS2 Red + Blue two-color composite for nebulae.

    Each band is autoleveled independently for dynamic range, then blue is scaled
    to 45% so Hα-dominated red luminance stays dominant. Synthetic green is blended
    from both so stars appear white rather than orange or magenta.
    """
    import math
    from PIL import Image
    red_data  = _skyview_band(ra_deg, dec_deg, fov_deg, pixels, "DSS2 Red")
    blue_data = _skyview_band(ra_deg, dec_deg, fov_deg, pixels, "DSS2 Blue")
    if not red_data:
        return None

    def _sky_subtract(img):
        """Subtract sky background — clips the bottom 30% to black so nebula sits on dark space."""
        from PIL import ImageOps
        return ImageOps.autocontrast(img, cutoff=(30, 0))

    r_ch = _sky_subtract(Image.open(io.BytesIO(red_data)).convert("L"))
    if blue_data:
        b_raw = _sky_subtract(Image.open(io.BytesIO(blue_data)).convert("L"))
        b_ch  = b_raw.point(lambda p: int(p * 0.50))
    else:
        b_ch = r_ch.point(lambda p: int(p * 0.22))

    # Arcsinh stretch on red for contrast without blowing bright cores
    scale = 3.0
    norm  = math.asinh(scale)
    r_ch = r_ch.point(lambda p: min(255, int(math.asinh(scale * p / 255) / norm * 255)))

    # Low green makes Hα-dominated nebulae deep red/crimson rather than orange.
    # Stars still appear orange-yellow (DSS Red is red-sensitive), which is natural.
    r_arr = list(r_ch.getdata())
    b_arr = list(b_ch.getdata())
    g_arr = [min(255, int(r * 0.18 + b * 0.45)) for r, b in zip(r_arr, b_arr)]
    g_ch = Image.new("L", r_ch.size)
    g_ch.putdata(g_arr)

    rgb = Image.merge("RGB", (r_ch, g_ch, b_ch))
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    return buf.getvalue()


def _dss_warm(ra_deg: float, dec_deg: float,
              fov_deg: float, pixels: int,
              obj_type: str = "") -> Optional[bytes]:
    """DSS fallback: natural 2-color composite for nebulae, warm amber tint for everything else."""
    if obj_type in ("Emission Nebula", "Supernova Remnant", "Reflection Nebula"):
        data = _dss_natural(ra_deg, dec_deg, fov_deg, pixels)
        if data:
            return data

    from PIL import Image
    red_data = _skyview_band(ra_deg, dec_deg, fov_deg, pixels, "DSS2 Red")
    if not red_data:
        return None
    lum = _autolevels(Image.open(io.BytesIO(red_data)).convert("L"))
    # Warm amber for galaxies / clusters
    r_ch = lum
    g_ch = lum.point(lambda p: int(p * 0.72))
    b_ch = lum.point(lambda p: int(p * 0.45))
    rgb = Image.merge("RGB", (r_ch, g_ch, b_ch))
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    return buf.getvalue()


def fetch_dso_image(
    name: str,
    ra: str,
    dec: str,
    size_arcmin: float,
    pixels: int = 300,
    obj_type: str = "",
) -> Optional[bytes]:
    """Return PNG bytes for a DSO, using local cache after first fetch."""
    if not ra or not dec:
        return None

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = name.replace(" ", "_").replace("/", "_")
    cache_path = _CACHE_DIR / f"{safe_name}.png"
    if cache_path.exists():
        return cache_path.read_bytes()

    try:
        ra_deg  = _ra_to_deg(ra)
        dec_deg = _dec_to_deg(dec)
        fov_deg = min(max(size_arcmin * 2.5 / 60.0, 0.25), 1.2)

        data = _sdss_server(ra_deg, dec_deg, fov_deg, pixels)
        if not data:
            _log.info("%s: SDSS unavailable, trying Legacy Survey", name)
            data = _legacy_survey(ra_deg, dec_deg, fov_deg, pixels)
        if not data and obj_type in ("Emission Nebula", "Supernova Remnant",
                                     "Reflection Nebula", "Planetary Nebula"):
            _log.info("%s: trying Wikipedia photo", name)
            data = _wikipedia_photo(name, "", pixels)
        if not data:
            _log.info("%s: trying DSS2 composite", name)
            data = _dss_warm(ra_deg, dec_deg, fov_deg, pixels, obj_type)

        if data:
            cache_path.write_bytes(data)
            _log.info("Cached %s (%d bytes)", name, len(data))
            return data

        _log.warning("All image sources failed for %s", name)
        return None

    except Exception as exc:
        _log.warning("Failed to fetch image for %s: %s", name, exc)
        return None


def clear_cache() -> int:
    if not _CACHE_DIR.exists():
        return 0
    count = 0
    for f in _CACHE_DIR.glob("*.png"):
        f.unlink()
        count += 1
    return count
