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
    "mango":      {"path": "/images/food/mango.webp",      "alt": "A cartoon mango",        "category": "food"},
    "apple":      {"path": "/images/food/apple.webp",      "alt": "A cartoon apple",        "category": "food"},
    "banana":     {"path": "/images/food/banana.webp",     "alt": "A cartoon banana",       "category": "food"},
    "rice":       {"path": "/images/food/rice.webp",       "alt": "A cartoon bowl of rice", "category": "food"},
    "roti":       {"path": "/images/food/roti.webp",       "alt": "A cartoon roti",         "category": "food"},
    "milk":       {"path": "/images/food/milk.webp",       "alt": "A cartoon glass of milk","category": "food"},
    "egg":        {"path": "/images/food/egg.webp",        "alt": "A cartoon egg",          "category": "food"},
    "vegetables": {"path": "/images/food/vegetables.webp", "alt": "Cartoon vegetables",     "category": "food"},

    # ── Body Parts (Science: My Body, Our Senses, Human Body) ──
    "human_body":    {"path": "/images/body/human_body.webp",    "alt": "A cartoon child's body", "category": "body"},
    "eye":           {"path": "/images/body/eye.webp",           "alt": "A cartoon eye",          "category": "body"},
    "ear":           {"path": "/images/body/ear.webp",           "alt": "A cartoon ear",          "category": "body"},
    "nose":          {"path": "/images/body/nose.webp",          "alt": "A cartoon nose",         "category": "body"},
    "tongue":        {"path": "/images/body/tongue.webp",        "alt": "A cartoon tongue",       "category": "body"},
    "hand":          {"path": "/images/body/hand.webp",          "alt": "A cartoon hand",         "category": "body"},
    "foot":          {"path": "/images/body/foot.webp",          "alt": "A cartoon foot",         "category": "body"},
    "brain":         {"path": "/images/body/brain.webp",         "alt": "A cartoon brain",        "category": "body"},
    "heart_organ":   {"path": "/images/body/heart_organ.webp",   "alt": "A cartoon heart organ",  "category": "body"},
    "lungs":         {"path": "/images/body/lungs.webp",         "alt": "A cartoon pair of lungs","category": "body"},
    "skeleton":      {"path": "/images/body/skeleton.webp",      "alt": "A cartoon skeleton",     "category": "body"},
    "stomach":       {"path": "/images/body/stomach.webp",       "alt": "A cartoon stomach",      "category": "body"},
    "teeth":         {"path": "/images/body/teeth.webp",         "alt": "A cartoon teeth",        "category": "body"},

    # ── Science (States of Matter, Force, Energy, Ecosystem) ──
    "solid_liquid_gas": {"path": "/images/science/solid_liquid_gas.webp", "alt": "Solid liquid gas states", "category": "science"},
    "ice_cube":      {"path": "/images/science/ice_cube.webp",      "alt": "A cartoon ice cube",       "category": "science"},
    "water_drop":    {"path": "/images/science/water_drop.webp",    "alt": "A cartoon water drop",     "category": "science"},
    "steam":         {"path": "/images/science/steam.webp",         "alt": "A cartoon steam cloud",    "category": "science"},
    "thermometer":   {"path": "/images/science/thermometer.webp",   "alt": "A cartoon thermometer",    "category": "science"},
    "magnet":        {"path": "/images/science/magnet.webp",        "alt": "A cartoon magnet",         "category": "science"},
    "spring":        {"path": "/images/science/spring.webp",        "alt": "A cartoon spring",         "category": "science"},
    "wheel":         {"path": "/images/science/wheel.webp",         "alt": "A cartoon wheel",          "category": "science"},
    "pulley":        {"path": "/images/science/pulley.webp",        "alt": "A cartoon pulley",         "category": "science"},
    "lever":         {"path": "/images/science/lever.webp",         "alt": "A cartoon lever/seesaw",   "category": "science"},
    "inclined_plane":{"path": "/images/science/inclined_plane.webp","alt": "A cartoon ramp",           "category": "science"},
    "light_bulb":    {"path": "/images/science/light_bulb.webp",    "alt": "A cartoon light bulb",     "category": "science"},
    "battery":       {"path": "/images/science/battery.webp",       "alt": "A cartoon battery",        "category": "science"},
    "solar_panel":   {"path": "/images/science/solar_panel.webp",   "alt": "A cartoon solar panel",    "category": "science"},
    "wind_turbine":  {"path": "/images/science/wind_turbine.webp",  "alt": "A cartoon wind turbine",   "category": "science"},
    "photosynthesis":{"path": "/images/science/photosynthesis.webp","alt": "Photosynthesis diagram",   "category": "science"},
    "seed_germination":{"path":"/images/science/seed_germination.webp","alt":"Seed germination stages","category": "science"},
    "root":          {"path": "/images/science/root.webp",          "alt": "A cartoon plant root",     "category": "science"},
    "leaf":          {"path": "/images/science/leaf.webp",          "alt": "A cartoon green leaf",     "category": "science"},
    "food_chain":    {"path": "/images/science/food_chain.webp",    "alt": "A cartoon food chain",     "category": "science"},
    "water_cycle":   {"path": "/images/science/water_cycle.webp",   "alt": "A cartoon water cycle",    "category": "science"},
    "pollution":     {"path": "/images/science/pollution.webp",     "alt": "A cartoon pollution scene", "category": "science"},
    "recycle":       {"path": "/images/science/recycle.webp",       "alt": "A cartoon recycle symbol",  "category": "science"},

    # ── Space / Solar System (Science + GK) ──
    "sun":           {"path": "/images/space/sun.webp",          "alt": "A cartoon sun",            "category": "space"},
    "moon":          {"path": "/images/space/moon.webp",         "alt": "A cartoon moon",           "category": "space"},
    "earth":         {"path": "/images/space/earth.webp",        "alt": "A cartoon Earth",          "category": "space"},
    "mars":          {"path": "/images/space/mars.webp",         "alt": "A cartoon Mars",           "category": "space"},
    "jupiter":       {"path": "/images/space/jupiter.webp",      "alt": "A cartoon Jupiter",        "category": "space"},
    "saturn":        {"path": "/images/space/saturn.webp",       "alt": "A cartoon Saturn",         "category": "space"},
    "solar_system":  {"path": "/images/space/solar_system.webp", "alt": "A cartoon solar system",   "category": "space"},
    "rocket":        {"path": "/images/space/rocket.webp",       "alt": "A cartoon rocket",         "category": "space"},
    "astronaut":     {"path": "/images/space/astronaut.webp",    "alt": "A cartoon astronaut",      "category": "space"},
    "telescope":     {"path": "/images/space/telescope.webp",    "alt": "A cartoon telescope",      "category": "space"},
    "satellite":     {"path": "/images/space/satellite.webp",    "alt": "A cartoon satellite",      "category": "space"},

    # ── Landmarks (GK) ──
    "taj_mahal":        {"path": "/images/landmarks/taj_mahal.webp",        "alt": "A cartoon Taj Mahal",         "category": "landmark"},
    "red_fort":         {"path": "/images/landmarks/red_fort.webp",         "alt": "A cartoon Red Fort",          "category": "landmark"},
    "india_gate":       {"path": "/images/landmarks/india_gate.webp",       "alt": "A cartoon India Gate",        "category": "landmark"},
    "qutub_minar":      {"path": "/images/landmarks/qutub_minar.webp",     "alt": "A cartoon Qutub Minar",       "category": "landmark"},
    "gateway_of_india": {"path": "/images/landmarks/gateway_of_india.webp", "alt": "A cartoon Gateway of India",  "category": "landmark"},
    "golden_temple":    {"path": "/images/landmarks/golden_temple.webp",    "alt": "A cartoon Golden Temple",     "category": "landmark"},
    "eiffel_tower":     {"path": "/images/landmarks/eiffel_tower.webp",     "alt": "A cartoon Eiffel Tower",      "category": "landmark"},
    "statue_of_liberty":{"path": "/images/landmarks/statue_of_liberty.webp","alt": "A cartoon Statue of Liberty", "category": "landmark"},
    "great_wall":       {"path": "/images/landmarks/great_wall.webp",       "alt": "A cartoon Great Wall",        "category": "landmark"},
    "pyramids":         {"path": "/images/landmarks/pyramids.webp",         "alt": "Cartoon Egyptian pyramids",   "category": "landmark"},

    # ── National Symbols (GK) ──
    "indian_flag":      {"path": "/images/symbols/indian_flag.webp",      "alt": "Indian national flag",       "category": "symbol"},
    "ashoka_chakra":    {"path": "/images/symbols/ashoka_chakra.webp",    "alt": "Ashoka Chakra wheel",        "category": "symbol"},
    "national_emblem":  {"path": "/images/symbols/national_emblem.webp",  "alt": "Indian national emblem",     "category": "symbol"},
    "lotus_national":   {"path": "/images/symbols/lotus_national.webp",   "alt": "Lotus national flower",      "category": "symbol"},
    "tiger_national":   {"path": "/images/symbols/tiger_national.webp",   "alt": "Bengal tiger national animal","category": "symbol"},
    "peacock_national": {"path": "/images/symbols/peacock_national.webp", "alt": "Peacock national bird",       "category": "symbol"},
    "banyan_national":  {"path": "/images/symbols/banyan_national.webp",  "alt": "Banyan national tree",        "category": "symbol"},
    "mango_national":   {"path": "/images/symbols/mango_national.webp",   "alt": "Mango national fruit",        "category": "symbol"},
    "rupee_symbol":     {"path": "/images/symbols/rupee_symbol.webp",     "alt": "Indian Rupee symbol",          "category": "symbol"},

    # ── Geography (GK) ──
    "globe":            {"path": "/images/geography/globe.webp",           "alt": "A cartoon globe",             "category": "geography"},
    "world_map":        {"path": "/images/geography/world_map.webp",       "alt": "A cartoon world map",         "category": "geography"},
    "india_map":        {"path": "/images/geography/india_map.webp",       "alt": "A cartoon India map",         "category": "geography"},
    "compass":          {"path": "/images/geography/compass.webp",         "alt": "A cartoon compass",           "category": "geography"},
    "continent_asia":   {"path": "/images/geography/continent_asia.webp",  "alt": "A cartoon Asia continent",    "category": "geography"},
    "continent_africa": {"path": "/images/geography/continent_africa.webp","alt": "A cartoon Africa continent",  "category": "geography"},
    "continent_europe": {"path": "/images/geography/continent_europe.webp","alt": "A cartoon Europe continent",  "category": "geography"},

    # ── Computer Parts ──
    "desktop_computer": {"path": "/images/computer/desktop_computer.webp","alt": "A cartoon desktop computer",  "category": "computer"},
    "laptop":           {"path": "/images/computer/laptop.webp",          "alt": "A cartoon laptop",            "category": "computer"},
    "keyboard":         {"path": "/images/computer/keyboard.webp",        "alt": "A cartoon keyboard",          "category": "computer"},
    "mouse":            {"path": "/images/computer/mouse.webp",           "alt": "A cartoon computer mouse",    "category": "computer"},
    "monitor":          {"path": "/images/computer/monitor.webp",         "alt": "A cartoon monitor",           "category": "computer"},
    "cpu_tower":        {"path": "/images/computer/cpu_tower.webp",       "alt": "A cartoon CPU tower",         "category": "computer"},
    "printer":          {"path": "/images/computer/printer.webp",         "alt": "A cartoon printer",           "category": "computer"},
    "speaker":          {"path": "/images/computer/speaker.webp",         "alt": "A cartoon speaker",           "category": "computer"},
    "headphones":       {"path": "/images/computer/headphones.webp",      "alt": "A cartoon headphones",        "category": "computer"},
    "usb_drive":        {"path": "/images/computer/usb_drive.webp",       "alt": "A cartoon USB drive",         "category": "computer"},
    "tablet":           {"path": "/images/computer/tablet.webp",          "alt": "A cartoon tablet",            "category": "computer"},
    "cd_disc":          {"path": "/images/computer/cd_disc.webp",         "alt": "A cartoon CD disc",           "category": "computer"},

    # ── Health & Hygiene ──
    "toothbrush":       {"path": "/images/health/toothbrush.webp",     "alt": "A cartoon toothbrush",       "category": "health"},
    "soap":             {"path": "/images/health/soap.webp",           "alt": "A cartoon soap",             "category": "health"},
    "handwash":         {"path": "/images/health/handwash.webp",       "alt": "Cartoon child washing hands", "category": "health"},
    "comb":             {"path": "/images/health/comb.webp",           "alt": "A cartoon comb",             "category": "health"},
    "towel":            {"path": "/images/health/towel.webp",          "alt": "A cartoon towel",            "category": "health"},
    "water_bottle":     {"path": "/images/health/water_bottle.webp",   "alt": "A cartoon water bottle",     "category": "health"},
    "first_aid_kit":    {"path": "/images/health/first_aid_kit.webp",  "alt": "A cartoon first aid kit",    "category": "health"},
    "bandage":          {"path": "/images/health/bandage.webp",        "alt": "A cartoon bandage",          "category": "health"},
    "yoga_pose":        {"path": "/images/health/yoga_pose.webp",      "alt": "A cartoon child doing yoga", "category": "health"},
    "stretching":       {"path": "/images/health/stretching.webp",     "alt": "A cartoon child stretching", "category": "health"},
    "running":          {"path": "/images/health/running.webp",        "alt": "A cartoon child running",    "category": "health"},
    "sleeping":         {"path": "/images/health/sleeping.webp",       "alt": "A cartoon child sleeping",   "category": "health"},
    "food_pyramid":     {"path": "/images/health/food_pyramid.webp",   "alt": "A cartoon food pyramid",     "category": "health"},
    "balanced_meal":    {"path": "/images/health/balanced_meal.webp",  "alt": "A cartoon balanced meal",    "category": "health"},
    "junk_food":        {"path": "/images/health/junk_food.webp",      "alt": "Cartoon junk food crossed",  "category": "health"},
    "fruits_group":     {"path": "/images/health/fruits_group.webp",   "alt": "A cartoon group of fruits",  "category": "health"},

    # ── Weather & Seasons ──
    "sunny":         {"path": "/images/weather/sunny.webp",        "alt": "A cartoon sunny day",       "category": "weather"},
    "rainy":         {"path": "/images/weather/rainy.webp",        "alt": "A cartoon rainy day",       "category": "weather"},
    "cloudy":        {"path": "/images/weather/cloudy.webp",       "alt": "A cartoon cloudy sky",      "category": "weather"},
    "snowy":         {"path": "/images/weather/snowy.webp",        "alt": "A cartoon snowy scene",     "category": "weather"},
    "windy":         {"path": "/images/weather/windy.webp",        "alt": "A cartoon windy day",       "category": "weather"},
    "rainbow":       {"path": "/images/weather/rainbow.webp",      "alt": "A cartoon rainbow",         "category": "weather"},
    "umbrella":      {"path": "/images/weather/umbrella.webp",     "alt": "A cartoon umbrella",        "category": "weather"},
    "summer":        {"path": "/images/weather/summer.webp",       "alt": "A cartoon summer scene",    "category": "weather"},
    "winter":        {"path": "/images/weather/winter.webp",       "alt": "A cartoon winter scene",    "category": "weather"},
    "rainy_season":  {"path": "/images/weather/rainy_season.webp", "alt": "A cartoon monsoon scene",   "category": "weather"},
    "autumn":        {"path": "/images/weather/autumn.webp",       "alt": "A cartoon autumn scene",    "category": "weather"},
    "spring_season": {"path": "/images/weather/spring.webp",       "alt": "A cartoon spring scene",    "category": "weather"},

    # ── Family & Community ──
    "family_group":  {"path": "/images/family/family_group.webp",  "alt": "A cartoon family",          "category": "family"},
    "grandparents":  {"path": "/images/family/grandparents.webp",  "alt": "Cartoon grandparents",      "category": "family"},
    "mother":        {"path": "/images/family/mother.webp",        "alt": "A cartoon mother",          "category": "family"},
    "father":        {"path": "/images/family/father.webp",        "alt": "A cartoon father",          "category": "family"},
    "baby":          {"path": "/images/family/baby.webp",          "alt": "A cartoon baby",            "category": "family"},
    "teacher":       {"path": "/images/family/teacher.webp",       "alt": "A cartoon teacher",         "category": "family"},
    "doctor":        {"path": "/images/family/doctor.webp",        "alt": "A cartoon doctor",          "category": "family"},
    "police":        {"path": "/images/family/police.webp",        "alt": "A cartoon police officer",  "category": "family"},
    "farmer":        {"path": "/images/family/farmer.webp",        "alt": "A cartoon farmer",          "category": "family"},
    "postman":       {"path": "/images/family/postman.webp",       "alt": "A cartoon postman",         "category": "family"},

    # ── Transport ──
    "car":           {"path": "/images/transport/car.webp",           "alt": "A cartoon car",            "category": "transport"},
    "bus":           {"path": "/images/transport/bus.webp",           "alt": "A cartoon school bus",     "category": "transport"},
    "train":         {"path": "/images/transport/train.webp",         "alt": "A cartoon train",          "category": "transport"},
    "bicycle":       {"path": "/images/transport/bicycle.webp",       "alt": "A cartoon bicycle",        "category": "transport"},
    "airplane":      {"path": "/images/transport/airplane.webp",      "alt": "A cartoon airplane",       "category": "transport"},
    "boat":          {"path": "/images/transport/boat.webp",          "alt": "A cartoon boat",           "category": "transport"},
    "auto_rickshaw": {"path": "/images/transport/auto_rickshaw.webp", "alt": "A cartoon auto-rickshaw",  "category": "transport"},
    "bullock_cart":  {"path": "/images/transport/bullock_cart.webp",  "alt": "A cartoon bullock cart",   "category": "transport"},
    "ship":          {"path": "/images/transport/ship.webp",          "alt": "A cartoon ship",           "category": "transport"},
    "helicopter":    {"path": "/images/transport/helicopter.webp",    "alt": "A cartoon helicopter",     "category": "transport"},

    # ── Common Objects ──
    "clock":         {"path": "/images/objects/clock.webp",        "alt": "A cartoon wall clock",     "category": "object"},
    "calendar":      {"path": "/images/objects/calendar.webp",     "alt": "A cartoon calendar",       "category": "object"},
    "school_bag":    {"path": "/images/objects/school_bag.webp",   "alt": "A cartoon school bag",     "category": "object"},
    "pencil_box":    {"path": "/images/objects/pencil_box.webp",   "alt": "A cartoon pencil box",     "category": "object"},
    "book_open":     {"path": "/images/objects/book_open.webp",    "alt": "A cartoon open book",      "category": "object"},
    "notebook":      {"path": "/images/objects/notebook.webp",     "alt": "A cartoon notebook",       "category": "object"},
    "ruler":         {"path": "/images/objects/ruler.webp",        "alt": "A cartoon ruler",          "category": "object"},
    "scissors":      {"path": "/images/objects/scissors.webp",     "alt": "A cartoon scissors",       "category": "object"},
    "globe_desk":    {"path": "/images/objects/globe_desk.webp",   "alt": "A cartoon desk globe",     "category": "object"},
    "blackboard":    {"path": "/images/objects/blackboard.webp",   "alt": "A cartoon blackboard",     "category": "object"},
    "lunch_box":     {"path": "/images/objects/lunch_box.webp",    "alt": "A cartoon lunch box",      "category": "object"},
    "water_tap":     {"path": "/images/objects/water_tap.webp",    "alt": "A cartoon water tap",      "category": "object"},
    "dustbin":       {"path": "/images/objects/dustbin.webp",      "alt": "A cartoon dustbin",        "category": "object"},
    "broom":         {"path": "/images/objects/broom.webp",        "alt": "A cartoon broom",          "category": "object"},
    "lamp":          {"path": "/images/objects/lamp.webp",         "alt": "A cartoon oil lamp",       "category": "object"},
    "pot":           {"path": "/images/objects/pot.webp",          "alt": "A cartoon clay pot",       "category": "object"},

    # ── Festivals ──
    "diwali":           {"path": "/images/festivals/diwali.webp",           "alt": "A cartoon Diwali scene",     "category": "festival"},
    "holi":             {"path": "/images/festivals/holi.webp",             "alt": "A cartoon Holi scene",       "category": "festival"},
    "eid":              {"path": "/images/festivals/eid.webp",              "alt": "A cartoon Eid scene",        "category": "festival"},
    "christmas":        {"path": "/images/festivals/christmas.webp",        "alt": "A cartoon Christmas scene",  "category": "festival"},
    "republic_day":     {"path": "/images/festivals/republic_day.webp",     "alt": "Cartoon Republic Day",       "category": "festival"},
    "independence_day": {"path": "/images/festivals/independence_day.webp", "alt": "Cartoon Independence Day",   "category": "festival"},
    "raksha_bandhan":   {"path": "/images/festivals/raksha_bandhan.webp",   "alt": "A cartoon rakhi",            "category": "festival"},
    "ganesh_chaturthi": {"path": "/images/festivals/ganesh_chaturthi.webp", "alt": "A cartoon Ganesha",          "category": "festival"},

    # ── Musical Instruments ──
    "tabla":      {"path": "/images/instruments/tabla.webp",      "alt": "A cartoon tabla drums",    "category": "instrument"},
    "sitar":      {"path": "/images/instruments/sitar.webp",      "alt": "A cartoon sitar",          "category": "instrument"},
    "flute":      {"path": "/images/instruments/flute.webp",      "alt": "A cartoon flute",          "category": "instrument"},
    "harmonium":  {"path": "/images/instruments/harmonium.webp",  "alt": "A cartoon harmonium",      "category": "instrument"},
    "drum":       {"path": "/images/instruments/drum.webp",       "alt": "A cartoon drum",           "category": "instrument"},

    # ── Sports ──
    "cricket":       {"path": "/images/sports/cricket.webp",       "alt": "Cartoon cricket equipment", "category": "sport"},
    "football":      {"path": "/images/sports/football.webp",      "alt": "A cartoon football",        "category": "sport"},
    "badminton":     {"path": "/images/sports/badminton.webp",     "alt": "Cartoon badminton set",     "category": "sport"},
    "hockey":        {"path": "/images/sports/hockey.webp",        "alt": "Cartoon hockey equipment",  "category": "sport"},
    "kabaddi":       {"path": "/images/sports/kabaddi.webp",       "alt": "Cartoon children kabaddi",  "category": "sport"},
    "kho_kho":       {"path": "/images/sports/kho_kho.webp",       "alt": "Cartoon children kho-kho",  "category": "sport"},
    "swimming":      {"path": "/images/sports/swimming.webp",      "alt": "A cartoon child swimming",  "category": "sport"},
    "skipping_rope": {"path": "/images/sports/skipping_rope.webp", "alt": "A cartoon child skipping",  "category": "sport"},
}


# Categories relevant to each subject for prompt token savings
_SUBJECT_CATEGORIES: dict[str, list[str]] = {
    "maths": [],  # Maths uses SVG visuals, not image keywords
    "math": [],
    "mathematics": [],
    "science": ["animal", "plant", "body", "science", "space", "weather"],
    "evs": ["animal", "plant", "habitat", "food", "weather", "family", "transport", "object"],
    "english": ["object", "family"],
    "hindi": ["object", "family"],
    "gk": ["landmark", "symbol", "geography", "space", "instrument", "sport", "festival"],
    "computer": ["computer"],
    "health": ["health", "sport", "food"],
    "moral science": ["family", "festival"],
}


def get_available_keywords() -> list[str]:
    """Return all available image keywords for the LLM prompt."""
    return sorted(IMAGE_REGISTRY.keys())


def get_keywords_for_subject(subject: str) -> list[str]:
    """Return image keywords filtered by subject relevance.

    Maths returns empty (uses SVG visuals). Other subjects return only
    keywords whose category matches the subject's relevant categories.
    Falls back to all keywords for unknown subjects.
    """
    categories = _SUBJECT_CATEGORIES.get(subject.lower())
    if categories is None:
        # Unknown subject — return all keywords
        return get_available_keywords()
    if not categories:
        # Maths — no image keywords needed
        return []
    return sorted(
        kw for kw, info in IMAGE_REGISTRY.items()
        if info.get("category") in categories
    )


def resolve_keywords(keywords: list[str]) -> list[dict]:
    """Resolve image keywords to image entries. Skip unknown keywords."""
    return [IMAGE_REGISTRY[kw] for kw in keywords if kw in IMAGE_REGISTRY]
