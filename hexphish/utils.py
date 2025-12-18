def normalize_email(value):
    return value.strip().lower()


def parse_smtp_port(value):
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None
