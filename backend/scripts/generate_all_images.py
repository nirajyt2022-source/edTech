"""
Skolar — Batch Image Generation Script (Phase 2: All Subjects)
==============================================================

Generates cartoon clipart images for ALL subjects/topics where visuals add value.
Uses Gemini 2.5 Flash Image API (free tier: 500 images/day).

EXISTING (51 images — EVS Phase 1):
  animals/ (25), plants/ (10), habitats/ (8), food/ (8)

NEW images to generate by this script:
  science/       — body parts, states of matter, energy, solar system, etc.
  gk/            — landmarks, symbols, continents, space
  computer/      — hardware parts, keyboard, mouse, screen
  health/        — hygiene items, food groups, yoga poses, first aid
  objects/        — common classroom/household objects (shared across subjects)
  weather/       — seasons, weather types
  family/        — family members, community helpers
  body/          — human body parts, senses
  transport/     — vehicles (for EVS/GK topics)
  flags_symbols/ — Indian national symbols, flag

Usage:
    cd backend
    pip install google-genai Pillow --break-system-packages
    python scripts/generate_all_images.py

Requires: GEMINI_API_KEY environment variable
"""

import os
import sys
import time
from pathlib import Path
from io import BytesIO

try:
    from google import genai
    from google.genai import types
    from PIL import Image
except ImportError:
    print("Install dependencies: pip install google-genai Pillow --break-system-packages")
    sys.exit(1)

# ── Config ──
API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("gemini_api_key")
if not API_KEY:
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

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
FRONTEND_IMAGES = PROJECT_ROOT / "frontend" / "public" / "images"
BACKEND_IMAGES = SCRIPT_DIR.parent / "app" / "data" / "images"

# ── Consistent style prompt ──
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

# =============================================================================
# IMAGE DEFINITIONS — organized by category
# =============================================================================
# Only NEW images that don't already exist in the EVS set (animals/plants/habitats/food)

IMAGES = {

    # ── SCIENCE: Class 1-5 topics ──────────────────────────────────────────
    # Covers: My Body, Our Senses, Human Body, States of Matter, Force & Motion,
    #         Simple Machines, Photosynthesis, Solar System, Ecosystem, Energy

    "body": {
        "human_body":     "A simple cartoon outline of a child's body with arms and legs visible, front-facing, smiling",
        "eye":            "A cartoon close-up of a human eye with eyelashes, colorful iris",
        "ear":            "A cartoon human ear, simple and clear",
        "nose":           "A cartoon human nose, simple side view",
        "tongue":         "A cartoon open mouth showing the tongue, friendly expression",
        "hand":           "A cartoon child's hand with five fingers spread out, palm facing forward",
        "foot":           "A cartoon child's foot, simple side view",
        "brain":          "A simple cartoon brain in pink, friendly-looking with a smile",
        "heart_organ":    "A cartoon anatomical heart (not valentine), simple red with blue vessels",
        "lungs":          "A cartoon pair of lungs in pink/light blue, simple and clear",
        "skeleton":       "A friendly cartoon skeleton standing and waving, non-scary",
        "stomach":        "A cartoon stomach organ, simple illustration",
        "teeth":          "A cartoon row of white teeth with a toothbrush, smiling",
    },

    "science": {
        # States of matter
        "solid_liquid_gas":  "Three cartoon icons in a row: an ice cube (solid), a water drop (liquid), and a steam cloud (gas)",
        "ice_cube":          "A cartoon blue-white ice cube, slightly melting",
        "water_drop":        "A cartoon blue water droplet with a friendly face",
        "steam":             "A cartoon white steam cloud rising from a cup",
        "thermometer":       "A cartoon red thermometer showing temperature",

        # Force and motion
        "magnet":            "A cartoon red and blue horseshoe magnet with attraction lines",
        "spring":            "A cartoon coiled metal spring, stretched slightly",
        "wheel":             "A cartoon wooden wheel with spokes",
        "pulley":            "A cartoon simple pulley with rope and weight",
        "lever":             "A cartoon seesaw/lever with a triangle fulcrum",
        "inclined_plane":    "A cartoon ramp/inclined plane with a ball rolling down",

        # Energy
        "light_bulb":        "A cartoon glowing yellow light bulb, turned on",
        "battery":           "A cartoon battery with + and - symbols, red and black",
        "solar_panel":       "A cartoon blue solar panel angled toward a smiling sun",
        "wind_turbine":      "A cartoon white wind turbine with blades spinning",

        # Photosynthesis / plant science
        "photosynthesis":    "A cartoon diagram showing a green plant with arrows: sun shining down, CO2 going in, O2 coming out",
        "seed_germination":  "A cartoon sequence: seed → sprout → small plant, three stages in a row",
        "root":              "A cartoon plant showing visible roots underground in brown soil",
        "leaf":              "A single cartoon green leaf with visible veins",

        # Ecosystem
        "food_chain":        "A cartoon simple food chain: grass → grasshopper → frog → snake → eagle, with arrows",
        "water_cycle":       "A cartoon water cycle: ocean → cloud → rain → river → ocean, with arrows and sun",
        "pollution":         "A cartoon factory with dark smoke coming from chimney, grey clouds",
        "recycle":           "A cartoon green recycling symbol (three arrows in triangle)",
    },

    # ── SOLAR SYSTEM / SPACE: GK + Science ─────────────────────────────────
    "space": {
        "sun":           "A cartoon bright yellow smiling sun with rays",
        "moon":          "A cartoon crescent moon with a friendly face, stars around",
        "earth":         "A cartoon planet Earth showing blue oceans and green continents",
        "mars":          "A cartoon red planet Mars",
        "jupiter":       "A cartoon large Jupiter with colored bands",
        "saturn":        "A cartoon Saturn with its rings",
        "solar_system":  "A cartoon solar system with sun in center and planets orbiting, simple",
        "rocket":        "A cartoon red and white rocket ship flying through space with stars",
        "astronaut":     "A cartoon astronaut in white space suit, floating, waving",
        "telescope":     "A cartoon telescope on a tripod pointed at stars",
        "satellite":     "A cartoon satellite orbiting Earth with solar panels",
    },

    # ── GK: Landmarks, Symbols, Geography ──────────────────────────────────
    "landmarks": {
        "taj_mahal":         "A cartoon white Taj Mahal with its dome and minarets, blue sky",
        "red_fort":          "A cartoon Red Fort of Delhi with red sandstone walls",
        "india_gate":        "A cartoon India Gate monument in New Delhi",
        "qutub_minar":       "A cartoon Qutub Minar tower, tall red sandstone",
        "gateway_of_india":  "A cartoon Gateway of India monument in Mumbai",
        "golden_temple":     "A cartoon Golden Temple of Amritsar reflecting in water",
        "eiffel_tower":      "A cartoon Eiffel Tower in Paris, grey metallic",
        "statue_of_liberty": "A cartoon green Statue of Liberty with torch",
        "great_wall":        "A cartoon Great Wall of China winding over mountains",
        "pyramids":          "Cartoon Egyptian pyramids with sphinx in desert",
    },

    "symbols": {
        "indian_flag":       "A cartoon Indian national flag (tricolor: saffron, white, green) with Ashoka Chakra in blue",
        "ashoka_chakra":     "A cartoon blue Ashoka Chakra wheel with 24 spokes",
        "national_emblem":   "A cartoon Indian national emblem (Lion Capital of Ashoka) in gold",
        "lotus_national":    "A cartoon pink lotus flower — national flower of India",
        "tiger_national":    "A cartoon Bengal tiger — national animal of India",
        "peacock_national":  "A cartoon peacock with feathers spread — national bird of India",
        "banyan_national":   "A cartoon banyan tree with aerial roots — national tree of India",
        "mango_national":    "A cartoon mango fruit — national fruit of India",
        "rupee_symbol":      "A cartoon Indian Rupee symbol (₹) in gold",
    },

    "geography": {
        "globe":             "A cartoon globe on a stand showing continents and oceans",
        "world_map":         "A simple cartoon flat world map showing 7 continents in different colors",
        "india_map":         "A cartoon outline map of India in orange/saffron color",
        "compass":           "A cartoon compass showing N, S, E, W directions",
        "continent_asia":    "A cartoon outline of Asia continent in yellow",
        "continent_africa":  "A cartoon outline of Africa continent in green",
        "continent_europe":  "A cartoon outline of Europe continent in blue",
    },

    # ── COMPUTER: Parts, Devices ───────────────────────────────────────────
    "computer": {
        "desktop_computer":  "A cartoon desktop computer with monitor, keyboard, and mouse on a desk",
        "laptop":            "A cartoon open laptop computer, blue screen",
        "keyboard":          "A cartoon computer keyboard seen from above, keys visible",
        "mouse":             "A cartoon computer mouse, grey with a scroll wheel",
        "monitor":           "A cartoon computer monitor/screen showing a colorful desktop",
        "cpu_tower":         "A cartoon CPU tower/system unit, grey box",
        "printer":           "A cartoon white printer printing a page",
        "speaker":           "A cartoon computer speaker with sound waves",
        "headphones":        "A cartoon pair of headphones, black with cushions",
        "usb_drive":         "A cartoon USB flash drive/pen drive",
        "tablet":            "A cartoon tablet device with colorful screen",
        "cd_disc":           "A cartoon shiny CD/DVD disc with rainbow reflection",
    },

    # ── HEALTH & PE: Hygiene, Food Groups, Yoga, First Aid ─────────────────
    "health": {
        "toothbrush":        "A cartoon colorful toothbrush with toothpaste",
        "soap":              "A cartoon bar of soap with bubbles around it",
        "handwash":          "A cartoon child washing hands with soap and water",
        "comb":              "A cartoon hair comb, simple",
        "towel":             "A cartoon folded clean towel",
        "water_bottle":      "A cartoon water bottle, blue, half-filled",
        "first_aid_kit":     "A cartoon red first aid kit box with white cross",
        "bandage":           "A cartoon adhesive bandage/band-aid, beige with white pad",
        "yoga_pose":         "A cartoon child doing a simple yoga tree pose (vrikshasana)",
        "stretching":        "A cartoon child stretching arms up, exercising",
        "running":           "A cartoon child running happily",
        "sleeping":          "A cartoon child sleeping peacefully in bed with zzz",
        "food_pyramid":      "A cartoon food pyramid showing grains at base, fruits/vegetables, dairy, proteins, fats at top",
        "balanced_meal":     "A cartoon plate divided into sections: rice, dal, vegetables, salad — Indian balanced meal",
        "junk_food":         "A cartoon crossed-out burger and chips (showing unhealthy food)",
        "fruits_group":      "A cartoon group of assorted fruits: apple, banana, orange, mango, grapes",
    },

    # ── WEATHER & SEASONS: EVS Class 1-2 ──────────────────────────────────
    "weather": {
        "sunny":         "A cartoon bright sun with a blue sky and white clouds",
        "rainy":         "A cartoon rain cloud with raindrops falling",
        "cloudy":        "A cartoon grey overcast sky with thick clouds",
        "snowy":         "A cartoon snowy scene with white snowflakes falling",
        "windy":         "A cartoon scene with trees bending in strong wind and leaves flying",
        "rainbow":       "A cartoon colorful rainbow arc with clouds on both ends",
        "umbrella":      "A cartoon open red umbrella",
        "summer":        "A cartoon summer scene: bright sun, green tree, child in shorts",
        "winter":        "A cartoon winter scene: snow on ground, child in sweater and cap",
        "rainy_season":  "A cartoon monsoon scene: dark clouds, heavy rain, puddles, child with umbrella",
        "autumn":        "A cartoon autumn scene: orange/brown falling leaves, bare tree",
        "spring":        "A cartoon spring scene: flowers blooming, butterflies, green grass",
    },

    # ── FAMILY & COMMUNITY: EVS Class 1-2 ─────────────────────────────────
    "family": {
        "family_group":      "A cartoon happy Indian family: father, mother, and two children standing together",
        "grandparents":      "A cartoon elderly Indian couple (grandmother in saree, grandfather with glasses)",
        "mother":            "A cartoon Indian mother in saree, smiling",
        "father":            "A cartoon Indian father in shirt, smiling",
        "baby":              "A cartoon cute baby crawling, smiling",
        "teacher":           "A cartoon female teacher at a blackboard with chalk",
        "doctor":            "A cartoon doctor in white coat with stethoscope",
        "police":            "A cartoon Indian police officer in khaki uniform",
        "farmer":            "A cartoon Indian farmer with turban, holding wheat/crops",
        "postman":           "A cartoon postman in uniform carrying letters",
    },

    # ── TRANSPORT: EVS/GK ──────────────────────────────────────────────────
    "transport": {
        "car":           "A cartoon red car, side view, simple",
        "bus":           "A cartoon yellow school bus, side view",
        "train":         "A cartoon Indian train (blue ICF coach) on tracks",
        "bicycle":       "A cartoon red bicycle with basket",
        "airplane":      "A cartoon white airplane flying through clouds",
        "boat":          "A cartoon small wooden boat on water",
        "auto_rickshaw": "A cartoon Indian auto-rickshaw (green and yellow)",
        "bullock_cart":  "A cartoon traditional Indian bullock cart with two bullocks",
        "ship":          "A cartoon large ship on ocean waves",
        "helicopter":    "A cartoon red helicopter flying",
    },

    # ── COMMON OBJECTS: Shared across subjects ─────────────────────────────
    "objects": {
        "clock":         "A cartoon wall clock showing 3 o'clock, round with numbers",
        "calendar":      "A cartoon desk calendar showing a month",
        "school_bag":    "A cartoon blue school backpack with books inside",
        "pencil_box":    "A cartoon open pencil box with pencils, eraser, and sharpener",
        "book_open":     "A cartoon open book with text lines visible",
        "notebook":      "A cartoon ruled notebook with spiral binding",
        "ruler":         "A cartoon wooden ruler with centimeter markings",
        "scissors":      "A cartoon pair of child-safe scissors, green handles",
        "globe_desk":    "A cartoon globe on a wooden desk stand",
        "blackboard":    "A cartoon green blackboard on easel with chalk writing 'ABC'",
        "lunch_box":     "A cartoon Indian tiffin/lunch box with compartments",
        "water_tap":     "A cartoon water tap/faucet with water flowing",
        "dustbin":       "A cartoon green dustbin/trash can with lid",
        "broom":         "A cartoon Indian jhadu/broom",
        "lamp":          "A cartoon oil lamp (diya) with flame",
        "pot":           "A cartoon clay pot (matka) brown with water",
    },

    # ── FESTIVALS / CULTURE: GK / Moral Science ───────────────────────────
    "festivals": {
        "diwali":        "A cartoon Diwali scene: lit diyas, rangoli pattern, firecrackers in sky",
        "holi":          "A cartoon Holi scene: children throwing colorful powder/gulal",
        "eid":           "A cartoon Eid scene: crescent moon, mosque silhouette, lanterns",
        "christmas":     "A cartoon Christmas scene: decorated tree with star on top, gifts",
        "republic_day":  "A cartoon Republic Day parade: Indian flag, soldiers marching",
        "independence_day": "A cartoon Independence Day: children waving Indian tricolor flags",
        "raksha_bandhan":  "A cartoon rakhi (decorative thread) with flowers and gems",
        "ganesh_chaturthi": "A cartoon friendly Ganesha idol with modak sweets",
    },

    # ── MUSICAL INSTRUMENTS: GK / Cultural ─────────────────────────────────
    "instruments": {
        "tabla":         "A cartoon pair of tabla drums, brown and black",
        "sitar":         "A cartoon sitar (Indian string instrument), wooden",
        "flute":         "A cartoon bamboo flute (bansuri), brown",
        "harmonium":     "A cartoon harmonium with bellows, wooden",
        "drum":          "A cartoon dhol/drum with sticks",
    },

    # ── SPORTS: GK / Health ────────────────────────────────────────────────
    "sports": {
        "cricket":       "A cartoon cricket bat and ball with stumps",
        "football":      "A cartoon black and white football/soccer ball",
        "badminton":     "A cartoon badminton racket and shuttlecock",
        "hockey":        "A cartoon hockey stick and ball on grass",
        "kabaddi":       "A cartoon two children playing kabaddi",
        "kho_kho":       "A cartoon children playing kho-kho in a line",
        "swimming":      "A cartoon child swimming in a pool with goggles",
        "skipping_rope": "A cartoon child jumping with a skipping rope",
    },
}


# =============================================================================
# Helper functions
# =============================================================================

def generate_image(client, prompt: str, retries: int = 2):
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
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    img_bytes = part.inline_data.data
                    return Image.open(BytesIO(img_bytes))
            print(f"    ⚠ No image in response (attempt {attempt + 1})")
        except Exception as e:
            print(f"    ✗ Error (attempt {attempt + 1}): {e}")
            if attempt < retries:
                time.sleep(5)
    return None


def save_image(img, path: Path, size: tuple = OUTPUT_SIZE):
    """Resize and save image as WebP."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = img.convert("RGBA")
    img.thumbnail(size, Image.LANCZOS)
    bg = Image.new("RGBA", size, (255, 255, 255, 255))
    offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
    bg.paste(img, offset, img)
    bg.convert("RGB").save(str(path), "WEBP", quality=85)


def main():
    client = genai.Client(api_key=API_KEY)

    total = sum(len(items) for items in IMAGES.values())
    generated = 0
    skipped = 0
    failed = []

    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║  Skolar Image Generator — Phase 2 (All Subjects) ║")
    print(f"╠══════════════════════════════════════════════════╣")
    print(f"║  Model: {MODEL:<40s} ║")
    print(f"║  Total images: {total:<33d} ║")
    print(f"║  Output: frontend/public/images/ + backend/      ║")
    print(f"╚══════════════════════════════════════════════════╝")
    print()

    for category, items in IMAGES.items():
        print(f"── {category.upper()} ({len(items)} images) {'─' * (40 - len(category))}") 

        for keyword, description in items.items():
            # Check if already exists (skip)
            frontend_path = FRONTEND_IMAGES / category / f"{keyword}.webp"
            if frontend_path.exists():
                skipped += 1
                print(f"  [{generated + skipped}/{total}] {keyword}... ⏭ exists")
                continue

            print(f"  [{generated + skipped + 1}/{total}] {keyword}...", end=" ", flush=True)

            img = generate_image(client, description)

            if img:
                # Save to both frontend and backend
                save_image(img, frontend_path)
                backend_path = BACKEND_IMAGES / category / f"{keyword}.webp"
                save_image(img, backend_path)
                generated += 1
                print(f"✓ ({img.width}x{img.height})")
            else:
                failed.append(f"{category}/{keyword}")
                print("✗ FAILED")

            # Rate limit: stay under 15 req/min
            time.sleep(4.5)

    print()
    print(f"═══════════════════════════════════════════════════")
    print(f" Done! Generated: {generated} | Skipped: {skipped} | Failed: {len(failed)}")
    print(f" Total images in library: {generated + skipped}")
    if failed:
        print(f" Failed ({len(failed)}): {', '.join(failed)}")
    print(f"═══════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
