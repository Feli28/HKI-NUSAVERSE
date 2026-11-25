"""Data 7 etnis yang dikenali model. `label` HARUS sama persis dengan model.classes_.

Teks di sini ringkasan netral untuk layar hasil. Isi lengkap (budaya, makanan, pakaian, sejarah)
sebaiknya nanti dipindah ke database dengan sumber jurnal yang bisa ditelusuri.
"""
import re

ETHNICITIES = [
    {
        "label": "Ambon", "name": "Ambon", "region": "Maluku",
        "summary": ("The Ambonese are the people of Ambon Island and nearby islands in Maluku, in eastern "
                    "Indonesia. Their culture blends local Maluku traditions with centuries of contact with "
                    "traders from across the world, and is known for its music, seafood cuisine, and the "
                    "legacy of the spice trade."),
    },
    {
        "label": "Batak", "name": "Batak", "region": "North Sumatra",
        "summary": ("The Batak are a group of related peoples from the highlands around Lake Toba in North "
                    "Sumatra, including the Toba, Karo, Simalungun, Pakpak, Angkola, and Mandailing. They are "
                    "known for their distinct languages, ulos woven cloth, clan (marga) system, and "
                    "traditional houses."),
    },
    {
        "label": "Chinese", "name": "Chinese", "region": "Throughout Indonesia",
        "summary": ("Chinese Indonesians (Tionghoa) are Indonesians of Chinese ancestry whose communities have "
                    "lived in the archipelago for centuries, especially in coastal trading towns. Their culture "
                    "blends Chinese traditions with local Indonesian influences, seen in festivals, cuisine, "
                    "and architecture."),
    },
    {
        "label": "Javanese", "name": "Javanese", "region": "Java",
        "summary": ("The Javanese are one of the largest ethnic groups in Indonesia, originating from Central "
                    "and East Java. They are known for their rich culture, language, and traditions, including "
                    "batik, gamelan music, and wayang performances."),
    },
    {
        "label": "Kalimantan", "name": "Kalimantan", "region": "Borneo",
        "summary": ("Kalimantan is the Indonesian part of the island of Borneo, home to many indigenous peoples, "
                    "including the Dayak groups, alongside Malay and other communities. Its cultures are closely "
                    "tied to rivers and rainforests, with distinctive longhouses, beadwork, and ceremonies."),
    },
    {
        "label": "Papuan", "name": "Papuan", "region": "Papua, New Guinea",
        "summary": ("The Papuan peoples are the indigenous communities of the island of New Guinea, including "
                    "Indonesia's Papua provinces. They are made up of hundreds of distinct groups, each with its "
                    "own language and customs, and are known for woodcarving, traditional dance, and strong ties "
                    "to land and community."),
    },
    {
        "label": "Toraja", "name": "Toraja", "region": "South Sulawesi",
        "summary": ("The Toraja are an ethnic group from the highlands of South Sulawesi. They are known for "
                    "their elaborate funeral ceremonies, tongkonan houses with boat-shaped roofs, and intricate "
                    "wood carvings."),
    },
]

LABELS = [e["label"] for e in ETHNICITIES]


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


for _e in ETHNICITIES:
    _e["slug"] = slugify(_e["label"])

_BY_LABEL = {e["label"]: e for e in ETHNICITIES}
_BY_SLUG = {e["slug"]: e for e in ETHNICITIES}


def by_label(label):
    """Data etnis untuk label model; label tak dikenal tetap menghasilkan entri dasar."""
    return _BY_LABEL.get(label) or {
        "label": label, "name": label, "slug": slugify(label), "region": "", "summary": ""}


def by_slug(slug):
    return _BY_SLUG.get(slug)
