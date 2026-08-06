"""Tests for the NEW badge transparency fix."""
import io
import os
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")


def test_badge_static_asset_served():
    r = requests.get(f"{BASE_URL}/new-badge.png", timeout=15)
    assert r.status_code == 200
    assert r.headers.get("content-type") == "image/png"
    assert 140_000 < len(r.content) < 200_000, f"unexpected size: {len(r.content)}"


def test_badge_pixel_transparency():
    r = requests.get(f"{BASE_URL}/new-badge.png", timeout=15)
    img = Image.open(io.BytesIO(r.content))
    assert img.mode == "RGBA", f"mode={img.mode}"
    w, h = img.size
    alpha = img.split()[-1]
    # corners fully transparent
    for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        assert alpha.getpixel(pt) == 0, f"corner {pt} alpha={alpha.getpixel(pt)}"
    hist = alpha.histogram()
    total = w * h
    assert hist[0] > 0, "no fully transparent pixels"
    assert hist[255] > 0, "no fully opaque pixels"
    semi = sum(hist[1:255])
    assert semi / total < 0.01, f"semi-transparent pixels {semi}/{total} = {semi/total:.3%}"
    print(f"OK: {w}x{h}, transparent={hist[0]/total:.1%}, opaque={hist[255]/total:.1%}, semi={semi/total:.3%}")


def test_menu_api_returns_is_new():
    r = requests.get(f"{BASE_URL}/api/menu", timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    # find classique
    classique = [i for i in items if i.get("id") == "9190e659-fd6f-45a0-b270-3941ee94b153"]
    assert classique, "Classique item not found"
    assert classique[0].get("is_new") is True
    assert classique[0].get("has_image") is True
    new_count = sum(1 for i in items if i.get("is_new"))
    assert new_count >= 1
    print(f"OK: {new_count} items with is_new=true out of {len(items)}")


def test_admin_login_still_works():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={
        "email": "chahineisgoated@gmail.com",
        "password": "BurgerTimes2026!"
    }, timeout=15)
    assert r.status_code == 200, r.text
    assert "access_token" in r.json() or "token" in r.json() or r.cookies
