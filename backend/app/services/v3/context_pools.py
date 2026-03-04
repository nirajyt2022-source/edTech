"""Context pools for worksheet variety — names, scenarios, rotation."""

import random

INDIAN_NAMES = [
    "Aarav",
    "Ananya",
    "Vihaan",
    "Diya",
    "Reyansh",
    "Saanvi",
    "Arjun",
    "Isha",
    "Kabir",
    "Myra",
    "Aditya",
    "Kiara",
    "Rohan",
    "Priya",
    "Vivaan",
    "Anika",
    "Krishna",
    "Zara",
    "Rudra",
    "Pari",
    "Atharv",
    "Navya",
    "Shaurya",
    "Aadhya",
    "Dhruv",
    "Riya",
    "Arnav",
    "Sara",
    "Dev",
    "Anvi",
    "Ishan",
    "Tara",
    "Kian",
    "Meera",
    "Yash",
    "Nisha",
    "Aryan",
    "Siya",
    "Neil",
    "Pooja",
    "Rahul",
    "Sneha",
    "Manav",
    "Kavya",
    "Sameer",
    "Tanvi",
    "Kunal",
    "Ritika",
]

CONTEXT_POOLS = {
    "Maths": [
        "shopping at mandi",
        "cooking at home",
        "sports day at school",
        "Diwali celebration",
        "train journey",
        "zoo visit",
        "birthday party",
        "garden planting",
        "classroom activity",
        "Holi festival",
        "bus ride to school",
        "library visit",
        "cricket match",
        "picnic in park",
        "temple fair",
        "school canteen",
        "post office visit",
        "railway station",
    ],
    "English": [
        "school classroom",
        "family dinner",
        "park visit",
        "birthday party",
        "rainy day at home",
        "school assembly",
        "market shopping",
        "bus journey",
        "story time",
        "letter writing",
        "playground",
        "library",
    ],
    "EVS": [
        "kitchen at home",
        "school garden",
        "neighborhood walk",
        "rainy day",
        "summer vacation",
        "market visit",
        "farm visit",
        "river bank",
        "village fair",
        "forest walk",
        "rooftop garden",
        "school field trip",
    ],
    "Science": [
        "science lab",
        "kitchen experiment",
        "garden observation",
        "nature walk",
        "weather observation",
        "home kitchen",
        "school playground",
        "farm visit",
        "hospital visit",
        "water treatment plant",
        "bird watching",
        "night sky",
    ],
    "Hindi": [
        "घर पर",
        "बाज़ार में",
        "विद्यालय में",
        "पार्क में",
        "रेलगाड़ी में",
        "मेला",
        "त्योहार",
        "रसोई में",
        "बगीचे में",
        "पुस्तकालय",
        "खेल का मैदान",
        "गाँव में",
    ],
    "GK": [
        "world tour",
        "museum visit",
        "map reading",
        "quiz competition",
        "newspaper reading",
        "documentary",
    ],
    "Computer": [
        "computer lab",
        "home desktop",
        "school office",
        "gaming session",
        "internet browsing",
        "typing class",
    ],
    "Health": [
        "morning routine",
        "school sports",
        "lunch break",
        "doctor visit",
        "yoga class",
        "playground",
    ],
    "Moral Science": [
        "school bus",
        "classroom sharing",
        "playground dispute",
        "helping at home",
        "new student in class",
        "festival celebration",
    ],
}

# Objects for maths word problems (per grade context)
MATHS_OBJECTS = {
    "1": [
        "apples",
        "mangoes",
        "books",
        "crayons",
        "marbles",
        "pencils",
        "flowers",
        "chocolates",
        "balloons",
        "stickers",
    ],
    "2": ["stamps", "stickers", "marbles", "books", "beads", "coins", "flowers", "cards", "shells", "stars"],
    "3": ["notebooks", "pencils", "rupees", "stickers", "pages", "students", "toys", "packets", "laddoos", "bangles"],
    "4": ["metres", "kilometres", "kilograms", "litres", "rupees", "pages", "tickets", "boxes", "bottles", "packets"],
    "5": [
        "kilometres",
        "kilograms",
        "litres",
        "rupees",
        "hours",
        "minutes",
        "metres",
        "grams",
        "millilitres",
        "degrees",
    ],
}


def pick_names(count: int, exclude: list[str] | None = None) -> list[str]:
    """Pick N unique Indian names, excluding any already used."""
    available = [n for n in INDIAN_NAMES if n not in (exclude or [])]
    return random.sample(available, min(count, len(available)))


def pick_contexts(subject: str, count: int, generation_offset: int = 0) -> list[str]:
    """Pick N contexts with rotation for variety across worksheets."""
    pool = CONTEXT_POOLS.get(subject, CONTEXT_POOLS["Maths"])
    start = (generation_offset * count) % len(pool)
    return [pool[(start + i) % len(pool)] for i in range(count)]


def pick_objects(grade_num: int, count: int) -> list[str]:
    """Pick N maths word problem objects for this grade."""
    pool = MATHS_OBJECTS.get(str(grade_num), MATHS_OBJECTS["3"])
    return random.sample(pool, min(count, len(pool)))
