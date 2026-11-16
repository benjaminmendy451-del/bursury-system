"""Gives every template the signed-in person's real name and initials (instead of the login username)."""


def person_name(user):
    """Real name for a user: the student's registered full name, else their Django name, else the username."""
    profile = getattr(user, "profile", None)
    name = (getattr(profile, "full_name", "") or "").strip()
    return name or user.get_full_name().strip() or user.get_username()


def initials(name):
    """'Amina Wanjiru Kamau' -> 'AK'; a single name gives one letter."""
    parts = [p for p in name.replace("-", " ").split() if p[:1].isalpha()]
    if not parts:
        return (name[:1] or "?").upper()
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def identity(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    name = person_name(user)
    return {"display_name": name, "first_name": name.split()[0], "initials": initials(name)}
