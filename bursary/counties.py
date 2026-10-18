"""The 47 counties of Kenya, used for the registration dropdown and for tidying old data."""

COUNTIES = [
    "Baringo", "Bomet", "Bungoma", "Busia", "Elgeyo-Marakwet", "Embu", "Garissa", "Homa Bay",
    "Isiolo", "Kajiado", "Kakamega", "Kericho", "Kiambu", "Kilifi", "Kirinyaga", "Kisii",
    "Kisumu", "Kitui", "Kwale", "Laikipia", "Lamu", "Machakos", "Makueni", "Mandera",
    "Marsabit", "Meru", "Migori", "Mombasa", "Murang'a", "Nairobi", "Nakuru", "Nandi",
    "Narok", "Nyamira", "Nyandarua", "Nyeri", "Samburu", "Siaya", "Taita-Taveta",
    "Tana River", "Tharaka-Nithi", "Trans Nzoia", "Turkana", "Uasin Gishu", "Vihiga",
    "Wajir", "West Pokot",
]

COUNTY_CHOICES = [("", "Select your county")] + [(name, name) for name in COUNTIES]


def _key(text):
    """Lower-case, no spaces/hyphens/apostrophes, no trailing 'county'."""
    text = (text or "").lower().replace("'", "").replace("-", " ").replace("’", "")
    text = " ".join(text.split())
    if text.endswith(" county"):
        text = text[: -len(" county")]
    return text.replace(" ", "")


_LOOKUP = {_key(name): name for name in COUNTIES}
_LOOKUP.update({"transnzoia": "Trans Nzoia", "muranga": "Murang'a", "elgeyomarakwet": "Elgeyo-Marakwet"})


def canonical_county(text):
    """Return the official spelling for a typed county name, or None if it isn't recognised."""
    return _LOOKUP.get(_key(text))
