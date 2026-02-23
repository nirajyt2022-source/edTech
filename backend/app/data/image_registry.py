"""
Curated image library for worksheet visuals.
Maps keywords to image paths served from frontend /images/ directory.
"""
from __future__ import annotations

IMAGE_REGISTRY: dict[str, dict] = {
    # ── Animals ──
    "cow":       {"path": "/images/animals/cow.webp",       "alt": "A cartoon cow",       "category": "animal"},
    "lion":      {"path": "/images/animals/lion.webp",      "alt": "A cartoon lion",      "category": "animal"},
    "tiger":     {"path": "/images/animals/tiger.webp",     "alt": "A cartoon tiger",     "category": "animal"},
    "elephant":  {"path": "/images/animals/elephant.webp",  "alt": "A cartoon elephant",  "category": "animal"},
    "monkey":    {"path": "/images/animals/monkey.webp",    "alt": "A cartoon monkey",    "category": "animal"},
    "parrot":    {"path": "/images/animals/parrot.webp",    "alt": "A cartoon parrot",    "category": "animal"},
    "fish":      {"path": "/images/animals/fish.webp",      "alt": "A cartoon fish",      "category": "animal"},
    "butterfly": {"path": "/images/animals/butterfly.webp", "alt": "A cartoon butterfly", "category": "animal"},
    "ant":       {"path": "/images/animals/ant.webp",       "alt": "A cartoon ant",       "category": "animal"},
    "spider":    {"path": "/images/animals/spider.webp",    "alt": "A cartoon spider",    "category": "animal"},
    "rabbit":    {"path": "/images/animals/rabbit.webp",    "alt": "A cartoon rabbit",    "category": "animal"},
    "horse":     {"path": "/images/animals/horse.webp",     "alt": "A cartoon horse",     "category": "animal"},
    "dog":       {"path": "/images/animals/dog.webp",       "alt": "A cartoon dog",       "category": "animal"},
    "cat":       {"path": "/images/animals/cat.webp",       "alt": "A cartoon cat",       "category": "animal"},
    "hen":       {"path": "/images/animals/hen.webp",       "alt": "A cartoon hen",       "category": "animal"},
    "duck":      {"path": "/images/animals/duck.webp",      "alt": "A cartoon duck",      "category": "animal"},
    "peacock":   {"path": "/images/animals/peacock.webp",   "alt": "A cartoon peacock",   "category": "animal"},
    "frog":      {"path": "/images/animals/frog.webp",      "alt": "A cartoon frog",      "category": "animal"},
    "snake":     {"path": "/images/animals/snake.webp",     "alt": "A cartoon snake",     "category": "animal"},
    "deer":      {"path": "/images/animals/deer.webp",      "alt": "A cartoon deer",      "category": "animal"},
    "bear":      {"path": "/images/animals/bear.webp",      "alt": "A cartoon bear",      "category": "animal"},
    "penguin":   {"path": "/images/animals/penguin.webp",   "alt": "A cartoon penguin",   "category": "animal"},
    "camel":     {"path": "/images/animals/camel.webp",     "alt": "A cartoon camel",     "category": "animal"},
    "tortoise":  {"path": "/images/animals/tortoise.webp",  "alt": "A cartoon tortoise",  "category": "animal"},
    "bee":       {"path": "/images/animals/bee.webp",       "alt": "A cartoon bee",       "category": "animal"},

    # ── Plants ──
    "tree":        {"path": "/images/plants/tree.webp",        "alt": "A cartoon tree",        "category": "plant"},
    "flower":      {"path": "/images/plants/flower.webp",      "alt": "A cartoon flower",      "category": "plant"},
    "rose":        {"path": "/images/plants/rose.webp",        "alt": "A cartoon rose",        "category": "plant"},
    "sunflower":   {"path": "/images/plants/sunflower.webp",   "alt": "A cartoon sunflower",   "category": "plant"},
    "tulsi":       {"path": "/images/plants/tulsi.webp",       "alt": "A cartoon tulsi plant", "category": "plant"},
    "mango_tree":  {"path": "/images/plants/mango_tree.webp",  "alt": "A cartoon mango tree",  "category": "plant"},
    "banyan_tree": {"path": "/images/plants/banyan_tree.webp", "alt": "A cartoon banyan tree", "category": "plant"},
    "cactus":      {"path": "/images/plants/cactus.webp",      "alt": "A cartoon cactus",      "category": "plant"},
    "lotus":       {"path": "/images/plants/lotus.webp",       "alt": "A cartoon lotus",       "category": "plant"},
    "neem":        {"path": "/images/plants/neem.webp",        "alt": "A cartoon neem tree",   "category": "plant"},

    # ── Habitats ──
    "forest":   {"path": "/images/habitats/forest.webp",   "alt": "A cartoon forest",   "category": "habitat"},
    "pond":     {"path": "/images/habitats/pond.webp",     "alt": "A cartoon pond",     "category": "habitat"},
    "desert":   {"path": "/images/habitats/desert.webp",   "alt": "A cartoon desert",   "category": "habitat"},
    "ocean":    {"path": "/images/habitats/ocean.webp",    "alt": "A cartoon ocean",    "category": "habitat"},
    "farm":     {"path": "/images/habitats/farm.webp",     "alt": "A cartoon farm",     "category": "habitat"},
    "mountain": {"path": "/images/habitats/mountain.webp", "alt": "A cartoon mountain", "category": "habitat"},
    "garden":   {"path": "/images/habitats/garden.webp",   "alt": "A cartoon garden",   "category": "habitat"},
    "nest":     {"path": "/images/habitats/nest.webp",     "alt": "A cartoon nest",     "category": "habitat"},

    # ── Food ──
    "mango":      {"path": "/images/food/mango.webp",      "alt": "A cartoon mango",      "category": "food"},
    "apple":      {"path": "/images/food/apple.webp",      "alt": "A cartoon apple",      "category": "food"},
    "banana":     {"path": "/images/food/banana.webp",     "alt": "A cartoon banana",     "category": "food"},
    "rice":       {"path": "/images/food/rice.webp",       "alt": "A cartoon bowl of rice", "category": "food"},
    "roti":       {"path": "/images/food/roti.webp",       "alt": "A cartoon roti",       "category": "food"},
    "milk":       {"path": "/images/food/milk.webp",       "alt": "A cartoon glass of milk", "category": "food"},
    "egg":        {"path": "/images/food/egg.webp",        "alt": "A cartoon egg",        "category": "food"},
    "vegetables": {"path": "/images/food/vegetables.webp", "alt": "Cartoon vegetables",   "category": "food"},
}


def get_available_keywords() -> list[str]:
    """Return all available image keywords for the LLM prompt."""
    return sorted(IMAGE_REGISTRY.keys())


def resolve_keywords(keywords: list[str]) -> list[dict]:
    """Resolve image keywords to image entries. Skip unknown keywords."""
    return [IMAGE_REGISTRY[kw] for kw in keywords if kw in IMAGE_REGISTRY]
