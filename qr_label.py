import hashlib
from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent

# ───────────── 폰트 ─────────────
# (경로, ttc 인덱스) 순서대로 시도. Streamlit Cloud는 packages.txt 에 fonts-nanum 추가
_FONT_CANDIDATES = [
    ("fonts/NanumGothicBold.ttf", 0),
    ("fonts/NanumGothicExtraBold.ttf", 0),
    ("/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf", 0),
    ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", 1),
    ("C:/Windows/Fonts/malgunbd.ttf", 0),
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
]
_BLACK_CANDIDATES = [
    ("fonts/NanumGothicExtraBold.ttf", 0),
    ("/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc", 1),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Black.ttc", 1),
]


def _font(size, black=False):
    cands = (_BLACK_CANDIDATES + _FONT_CANDIDATES) if black else _FONT_CANDIDATES
    for path, idx in cands:
        p = Path(path) if Path(path).is_absolute() else BASE / path
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size, index=idx)
            except Exception:
                continue
    return ImageFont.load_default()


# ───────────── 이미지 에셋  ─────────────
def _asset(name, width):
    """assets/<name> 을 불러와 내용 영역만 잘라 width 로 키움. 없으면 None."""
    p = BASE / "assets" / name
    if not p.exists():
        return None
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    bg.alpha_composite(im)
    g = bg.convert("L")
    box = g.point(lambda v: 255 if v < 200 else 0).getbbox()
    if box:
        g = g.crop(box)
    h = round(g.height * width / g.width)
    g = g.resize((width, h), Image.LANCZOS)
    # 확대로 흐려진 가장자리를 또렷하게 (명암 대비 강화)
    g = g.point(lambda v: 0 if v < 90 else 255 if v > 170 else int((v - 90) * 255 / 80))
    return g.convert("RGB")


# ───────────── 지역 구분코드 (임의 규칙) ─────────────
def zone_label(region, address):
    """'대전 유성 07-3' 형태.
    - 시/도 : 배송 지역
    - 시/군/구 : 상세주소 첫 단어에서 '시·군·구' 제거
    - 앞 숫자(01~30) : 시/군/구 + 도로명 해시 → 같은 길이면 같은 구역
    - 뒤 숫자(1~9)   : 전체 주소 해시 → 건물/호수 단위 구분
    """
    tokens = address.split()
    district = tokens[1] if len(tokens) > 1 else ""
    short = district
    if len(district) > 2 and district[-1] in "시군구":
        short = district[:-1]
    road = tokens[2] if len(tokens) > 2 else ""
    area = hashlib.sha256(f"{district}{road}".encode()).digest()[0] % 30 + 1
    sub = hashlib.sha256(" ".join(tokens).encode()).digest()[1] % 9 + 1
    return f"{region} {short}".strip(), f"{area:02d}-{sub}"

# ───────────── 메인: 라벨 생성 ─────────────
def make_label(order, qr_url, phone="010-123-4567", center="1516-1718"):
    S = 2  # 슈퍼샘플링 배율
    W, H = 1122, 1400
    img = Image.new("RGB", (W * S, H * S), "white")
    d = ImageDraw.Draw(img)
    BK, GR = (0, 0, 0), (96, 96, 96)

    def P(v):  # 좌표 스케일
        return v * S

    def text(xy, s, size, anchor="la", fill=BK, black=False):
        d.text((P(xy[0]), P(xy[1])), s, font=_font(P(size), black), fill=fill, anchor=anchor)

    # 테두리
    d.rounded_rectangle([P(22), P(22), P(1100), P(1358)], radius=P(42), outline=BK, width=P(5))

    # ── 로고 ──
    logo = _asset("logo.png", P(800))
    img.paste(logo, (P(165), P(62)))

    # ── 구역 코드 ──
    area_txt, code = zone_label(order["region"], order["address"])
    cf = _font(P(96), True)
    af = _font(P(66), True)
    right = P(1030)
    cw = d.textlength(code, font=cf)
    d.text((right, P(318)), code, font=cf, fill=BK, anchor="rs")
    d.text((right - cw - P(22), P(316)), area_txt, font=af, fill=BK, anchor="rs")

    # ── QR + 모서리 ──
    qr = qrcode.QRCode(border=0, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(qr_url)
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qsz = P(432)
    qimg = qimg.resize((qsz, qsz), Image.NEAREST)
    img.paste(qimg, (P(345), P(400)))
    bx1, by1, bx2, by2, ln, rr = P(300), P(360), P(822), P(858), P(70), P(22)
    w = P(5)
    for (cx_, cy_, sx, sy) in [(bx1, by1, 1, 1), (bx2, by1, -1, 1), (bx1, by2, 1, -1), (bx2, by2, -1, -1)]:
        d.line([(cx_ + sx * rr, cy_), (cx_ + sx * ln, cy_)], fill=BK, width=w)
        d.line([(cx_, cy_ + sy * rr), (cx_, cy_ + sy * ln)], fill=BK, width=w)
        ax0, ax1 = sorted([cx_, cx_ + sx * 2 * rr])
        ay0, ay1 = sorted([cy_, cy_ + sy * 2 * rr])
        start = {(1, 1): 180, (-1, 1): 270, (1, -1): 90, (-1, -1): 0}[(sx, sy)]
        d.arc([ax0, ay0, ax1, ay1], start, start + 90, fill=BK, width=w)

    # ── 연락처 ──
    for cy_, label in [(928, f"구매자 안심번호: {phone}"), (998, f"고객 센터 번호: {center}")]:
        d.ellipse([P(80), P(cy_ - 9), P(98), P(cy_ + 9)], fill=BK)
        text((118, cy_), label, 48, anchor="lm")

    # ── 취급 아이콘 4개 (구분선 포함 이미지) ──
    icons = _asset("icons.png", P(908))
    img.paste(icons, (P(107), P(1047)))
    d.line([(P(107), P(1047)), (P(1015), P(1047))], fill=(150, 150, 150), width=P(2))

    # ── 하단 배너 ──
    d.rounded_rectangle([P(60), P(1265), P(1062), P(1330)], radius=P(18), fill=GR)
    text((561, 1298), "배송 관계자 · 구매자 전용 / 개인정보는 표시되지 않습니다", 36,
         anchor="mm", fill="white")

    img = img.resize((W, H), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
