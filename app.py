import io
import os
import asyncio
import httpx
import base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
from concurrent.futures import ThreadPoolExecutor

# ================= ADJUSTMENT SETTINGS =================
AVATAR_ZOOM = 1.26
AVATAR_SHIFT_Y = 0
AVATAR_SHIFT_X = 0

BANNER_START_X = 0.25
BANNER_START_Y = 0.29
BANNER_END_X = 0.81
BANNER_END_Y = 0.65

# ================= API CONFIG =================
INFO_API_URL = "https://player-info-by-ckrpro.vercel.app/get"

BASE64 = "aHR0cHM6Ly9jZG4uanNkZWxpdnIubmV0L2doL1NoYWhHQ3JlYXRvci9pY29uQG1haW4vUE5H"
ICON_BASE_URL = base64.b64decode(BASE64).decode("utf-8")

FONT_FILE = "arial_unicode_bold.otf"
FONT_CHEROKEE = "NotoSansCherokee.ttf"

# ================= HTTP CLIENT =================
client = httpx.AsyncClient(
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    },
    timeout=20.0,
    follow_redirects=True
)

process_pool = ThreadPoolExecutor(max_workers=4)

# ================= FASTAPI LIFESPAN =================
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client.aclose()
    process_pool.shutdown()

app = FastAPI(lifespan=lifespan)

# ================= CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= FONT LOADER =================
def load_unicode_font(size, font_file=FONT_FILE):
    try:
        font_path = os.path.join(os.path.dirname(__file__), font_file)

        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)

    except Exception as e:
        print(f"Font load error: {e}")

    return ImageFont.load_default()

# ================= IMAGE FETCH =================
async def fetch_image_bytes(item_id):
    if not item_id or str(item_id) in ["0", "None", "null"]:
        print(f"DEBUG: Invalid image ID -> {item_id}")
        return None

    url = f"{ICON_BASE_URL}/{item_id}.png"

    try:
        response = await client.get(url)

        print(f"DEBUG: Fetch {url} -> {response.status_code}")

        if response.status_code == 200:
            return response.content

    except Exception as e:
        print(f"DEBUG: Image fetch error -> {e}")

    return None

# ================= IMAGE CONVERTER =================
def bytes_to_image(img_bytes):
    if img_bytes:
        try:
            return Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        except Exception as e:
            print(f"DEBUG: Image decode error -> {e}")

    return Image.new("RGBA", (400, 400), (180, 180, 180, 255))

# ================= TEXT DRAW =================
def is_cherokee(char):
    return (
        0x13A0 <= ord(char) <= 0x13FF
        or 0xAB70 <= ord(char) <= 0xABBF
    )

def draw_unicode_text(draw, x, y, text, font_main, font_alt, stroke):
    current_x = x

    for char in text:
        font = font_alt if is_cherokee(char) else font_main

        for dx in range(-stroke, stroke + 1):
            for dy in range(-stroke, stroke + 1):
                draw.text(
                    (current_x + dx, y + dy),
                    char,
                    font=font,
                    fill="black"
                )

        draw.text(
            (current_x, y),
            char,
            font=font,
            fill="white"
        )

        current_x += font.getlength(char)

# ================= IMAGE PROCESS =================
def process_banner_image(data, avatar_bytes, banner_bytes):
    avatar_img = bytes_to_image(avatar_bytes)
    banner_img = bytes_to_image(banner_bytes)

    level = str(data.get("AccountLevel", "0"))
    name = data.get("AccountName", "Unknown")
    guild = data.get("GuildName", "")

    TARGET_HEIGHT = 400

    # ================= AVATAR PROCESS =================
    zoom_size = int(TARGET_HEIGHT * AVATAR_ZOOM)

    avatar_img = avatar_img.resize(
        (zoom_size, zoom_size),
        Image.LANCZOS
    )

    left = (zoom_size - TARGET_HEIGHT) // 2 - AVATAR_SHIFT_X
    top = (zoom_size - TARGET_HEIGHT) // 2 - AVATAR_SHIFT_Y

    avatar_img = avatar_img.crop(
        (
            left,
            top,
            left + TARGET_HEIGHT,
            top + TARGET_HEIGHT
        )
    )

    avatar_width, avatar_height = avatar_img.size

    # ================= BANNER PROCESS =================
    banner_width, banner_height = banner_img.size

    if banner_width > 100 and banner_height > 100:
        banner_img = banner_img.rotate(3, expand=True)

        rotated_width, rotated_height = banner_img.size

        crop_left = rotated_width * BANNER_START_X
        crop_top = rotated_height * BANNER_START_Y
        crop_right = rotated_width * BANNER_END_X
        crop_bottom = rotated_height * BANNER_END_Y

        banner_img = banner_img.crop(
            (
                crop_left,
                crop_top,
                crop_right,
                crop_bottom
            )
        )

    banner_width, banner_height = banner_img.size

    aspect_ratio = (
        banner_width / banner_height
        if banner_height > 0
        else 2.0
    )

    new_banner_width = int(TARGET_HEIGHT * aspect_ratio * 2)

    banner_img = banner_img.resize(
        (new_banner_width, TARGET_HEIGHT),
        Image.LANCZOS
    )

    # ================= FINAL CANVAS =================
    final_width = avatar_width + new_banner_width

    combined = Image.new(
        "RGBA",
        (final_width, TARGET_HEIGHT),
        (0, 0, 0, 255)
    )

    combined.paste(avatar_img, (0, 0))
    combined.paste(banner_img, (avatar_width, 0))

    draw = ImageDraw.Draw(combined)

    # ================= FONTS =================
    font_large = load_unicode_font(125)
    font_large_alt = load_unicode_font(125, FONT_CHEROKEE)

    font_small = load_unicode_font(95)
    font_small_alt = load_unicode_font(95, FONT_CHEROKEE)

    font_level = load_unicode_font(50)

    # ================= DRAW TEXT =================
    draw_unicode_text(
        draw,
        avatar_width + 65,
        40,
        name,
        font_large,
        font_large_alt,
        4
    )

    draw_unicode_text(
        draw,
        avatar_width + 65,
        220,
        guild,
        font_small,
        font_small_alt,
        3
    )

    # ================= LEVEL BOX =================
    level_text = f"Lvl.{level}"

    bbox = draw.textbbox(
        (0, 0),
        level_text,
        font=font_level
    )

    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    box_x1 = final_width - text_width - 60
    box_y1 = TARGET_HEIGHT - text_height - 50

    box_x2 = final_width
    box_y2 = TARGET_HEIGHT

    draw.rectangle(
        [box_x1, box_y1, box_x2, box_y2],
        fill="black"
    )

    draw.text(
        (final_width - text_width - 30,
         TARGET_HEIGHT - text_height - 40),
        level_text,
        font=font_level,
        fill="white"
    )

    # ================= EXPORT =================
    output = io.BytesIO()

    combined.save(output, format="PNG")

    output.seek(0)

    return output

# ================= MAIN ROUTE =================
@app.get("/profile")
async def get_profile(uid: str):
    if not uid:
        raise HTTPException(
            status_code=400,
            detail="UID is required"
        )

    # ================= PLAYER INFO API =================
    try:
        response = await client.get(
            f"{INFO_API_URL}?uid={uid}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"API request failed: {e}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Failed to fetch player info"
        )

    try:
        data = response.json()

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Invalid JSON response"
        )

    # ================= DATA EXTRACTION =================
    account = data.get("AccountInfo", {})
    captain = data.get("captainBasicInfo", {})
    guild = data.get("GuildInfo", {})

    if not account:
        raise HTTPException(
            status_code=404,
            detail="Account not found"
        )

    # ================= IDS =================
    avatar_id = (
        account.get("AccountAvatarId")
        or captain.get("headPic")
    )

    banner_id = (
        account.get("AccountBannerId")
        or captain.get("bannerId")
    )

    print(
        f"DEBUG: Avatar ID -> {avatar_id} | "
        f"Banner ID -> {banner_id}"
    )

    # ================= FETCH IMAGES =================
    avatar_task = fetch_image_bytes(avatar_id)
    banner_task = fetch_image_bytes(banner_id)

    avatar_bytes, banner_bytes = await asyncio.gather(
        avatar_task,
        banner_task
    )

    # ================= BANNER DATA =================
    banner_data = {
        "AccountLevel": account.get("AccountLevel", "0"),
        "AccountName": (
            account.get("AccountName")
            or captain.get("nickname")
            or "Unknown"
        ),
        "GuildName": guild.get("GuildName", "")
    }

    # ================= THREAD PROCESS =================
    loop = asyncio.get_running_loop()

    img_io = await loop.run_in_executor(
        process_pool,
        process_banner_image,
        banner_data,
        avatar_bytes,
        banner_bytes
    )

    return Response(
        content=img_io.getvalue(),
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=300"
        }
    )

# ================= START SERVER =================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=5000
    )