"""
Batch generate cartoon clipart images for EVS worksheets using Gemini image generation.

Usage:
    cd backend
    python scripts/generate_evs_images.py

Requires: GEMINI_API_KEY env var (same one used for worksheet generation)
"""

import os
import sys
import time
from pathlib import Path
from io import BytesIO

# pip install google-genai Pillow
from google import genai
from google.genai import types
from PIL import Image

# ── Config ──
API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("gemini_api_key")
if not API_KEY:
    # Try loading from .env or config
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from app.core.config import get_settings
        API_KEY = get_settings().gemini_api_key
    except Exception:
        pass

if not API_KEY:
    print("ERROR: Set GEMINI_API_KEY environment variable")
    sys.exit(1)

MODEL = "gemini-2.5-flash-image"
OUTPUT_SIZE = (256, 256)

# Base directories
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
FRONTEND_IMAGES = PROJECT_ROOT / "frontend" / "public" / "images"
BACKEND_IMAGES = SCRIPT_DIR.parent / "app" / "data" / "images"

# ── Style prompt (consistent across all images) ──
STYLE_PROMPT = """
Style requirements:
- Simple cartoon illustration suitable for children aged 5-10
- Flat design with clean outlines and bright, cheerful colors
- White or transparent background
- No text, no labels, no watermarks
- Single subject centered in frame
- Friendly and non-scary appearance
- Educational clipart style similar to NCERT textbook illustrations
- The image should be clearly recognizable even at small sizes (64x64 pixels)
"""

# ── Image definitions ──
IMAGES = {
    "animals": {
        "cow": "A friendly cartoon brown and white cow standing, facing slightly left, with a gentle smile",
        "lion": "A cheerful cartoon lion with a big golden mane, sitting proudly",
        "tiger": "A cute cartoon tiger with orange and black stripes, walking",
        "elephant": "A happy cartoon Indian elephant with small tusks, trunk raised slightly",
        "monkey": "A playful cartoon brown monkey hanging from a branch, smiling",
        "parrot": "A colorful cartoon Indian parrot (green with red beak), perched on a branch",
        "fish": "A bright cartoon orange fish swimming, with bubbles around it",
        "butterfly": "A beautiful cartoon butterfly with colorful wings (blue and yellow)",
        "ant": "A tiny cartoon black ant carrying a leaf, looking cheerful",
        "spider": "A cute cartoon spider with a small web, non-scary, friendly looking",
        "rabbit": "A soft cartoon white rabbit with long ears, sitting",
        "horse": "A strong cartoon brown horse standing in a field",
        "dog": "A friendly cartoon brown puppy with floppy ears, wagging tail",
        "cat": "A cute cartoon orange tabby cat sitting, with whiskers",
        "hen": "A cartoon red hen with small yellow chicks nearby",
        "duck": "A cheerful cartoon yellow duck swimming in water",
        "peacock": "A magnificent cartoon Indian peacock with feathers displayed in full fan",
        "frog": "A happy cartoon green frog sitting on a lily pad",
        "snake": "A friendly cartoon green snake coiled up, non-scary, smiling",
        "deer": "A graceful cartoon spotted deer (chital) standing in grass",
        "bear": "A friendly cartoon brown bear standing on all fours",
        "penguin": "A cute cartoon black and white penguin standing on ice",
        "camel": "A cartoon brown camel with one hump standing in sand",
        "tortoise": "A slow cartoon green tortoise with a patterned shell, walking",
        "bee": "A busy cartoon bee with yellow and black stripes, tiny wings buzzing",
    },
    "plants": {
        "tree": "A simple cartoon green tree with a brown trunk and round leafy top",
        "flower": "A cheerful cartoon red flower with green stem and leaves",
        "rose": "A beautiful cartoon red rose with green thorny stem",
        "sunflower": "A tall cartoon yellow sunflower with brown center, facing forward",
        "lotus": "A cartoon pink lotus flower floating on water with green leaves",
        "mango_tree": "A cartoon mango tree with green leaves and yellow mangoes hanging",
        "banyan_tree": "A large cartoon banyan tree with hanging aerial roots",
        "cactus": "A cartoon green cactus with small flowers on top, in desert sand",
        "tulsi": "A cartoon tulsi (holy basil) plant in a small pot, with green leaves",
        "neem": "A cartoon neem tree with long thin green leaves",
    },
    "habitats": {
        "forest": "A cartoon dense green forest with many trees, birds, and a pathway",
        "pond": "A cartoon blue pond with lily pads, a frog, and reeds around the edges",
        "desert": "A cartoon sandy desert with a cactus, sand dunes, and bright sun",
        "ocean": "A cartoon blue ocean with waves, a fish jumping, and a boat in the distance",
        "farm": "A cartoon green farm with a red barn, fence, and crops growing",
        "mountain": "A cartoon snow-capped mountain with green base and blue sky",
        "garden": "A cartoon colorful garden with flowers, a butterfly, and a small path",
        "nest": "A cartoon bird nest made of twigs on a tree branch, with small eggs inside",
    },
    "food": {
        "mango": "A cartoon ripe yellow-orange Indian mango fruit with a green leaf attached",
        "apple": "A cartoon shiny red apple with a small green leaf on top",
        "banana": "A cartoon bunch of yellow bananas",
        "rice": "A cartoon white bowl of steaming rice with a spoon",
        "roti": "A cartoon round golden-brown Indian chapati/roti on a plate",
        "milk": "A cartoon glass of white milk, full, with a small splash",
        "egg": "A cartoon white egg and a cracked egg showing yellow yolk",
        "vegetables": "A cartoon group of colorful vegetables: carrot, tomato, potato, green beans",
    },
}


def generate_image(client: genai.Client, prompt: str, retries: int = 2) -> Image.Image | None:
    """Generate a single image via Gemini API."""
    full_prompt = f"{prompt}\n\n{STYLE_PROMPT}"

    for attempt in range(retries + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )

            # Extract image from response
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    img_bytes = part.inline_data.data
                    img = Image.open(BytesIO(img_bytes))
                    return img

            print(f"    ⚠ No image in response (attempt {attempt + 1})")

        except Exception as e:
            print(f"    ✗ Error (attempt {attempt + 1}): {e}")
            if attempt < retries:
                time.sleep(5)  # Rate limit backoff

    return None


def save_image(img: Image.Image, path: Path, size: tuple = OUTPUT_SIZE):
    """Resize and save image as WebP."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Resize to target size, maintaining aspect ratio with padding
    img = img.convert("RGBA")
    img.thumbnail(size, Image.LANCZOS)

    # Create white background and paste centered
    bg = Image.new("RGBA", size, (255, 255, 255, 255))
    offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
    bg.paste(img, offset, img)

    # Save as WebP
    bg.convert("RGB").save(str(path), "WEBP", quality=85)


def main():
    client = genai.Client(api_key=API_KEY)

    total = sum(len(items) for items in IMAGES.values())
    generated = 0
    failed = []

    print(f"Generating {total} cartoon images via Gemini API...")
    print(f"Model: {MODEL}")
    print(f"Output: {FRONTEND_IMAGES}")
    print()

    for category, items in IMAGES.items():
        print(f"── {category.upper()} ({len(items)} images) ──")

        for keyword, description in items.items():
            print(f"  [{generated + 1}/{total}] {keyword}...", end=" ", flush=True)

            img = generate_image(client, description)

            if img:
                # Save to frontend/public/images/
                frontend_path = FRONTEND_IMAGES / category / f"{keyword}.webp"
                save_image(img, frontend_path)

                # Save to backend/app/data/images/
                backend_path = BACKEND_IMAGES / category / f"{keyword}.webp"
                save_image(img, backend_path)

                generated += 1
                print(f"✓ saved ({img.width}x{img.height})")
            else:
                failed.append(f"{category}/{keyword}")
                print("✗ FAILED")

            # Rate limit: ~4 req/sec to stay under 15 req/min
            time.sleep(4)

    print()
    print("═══════════════════════════════════════")
    print(f"Done! Generated {generated}/{total} images")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed)}")
    print(f"Frontend images: {FRONTEND_IMAGES}")
    print(f"Backend images:  {BACKEND_IMAGES}")
    print("═══════════════════════════════════════")


if __name__ == "__main__":
    main()
