"""Shared patient folder and filename conventions (underscores, no spaces)."""


def to_pascalcase(text: str) -> str:
    """Convert text to Title Case (capitalize first letter of each word)."""
    return " ".join(word.capitalize() for word in (text or "").split())


def name_slug_part(text: str) -> str:
    """PascalCase name field as an underscore-safe filename segment."""
    return "_".join(to_pascalcase(text).split())


def patient_file_slug(patient_id, first_name: str, last_name: str) -> str:
    """e.g. 227738_Paige_Pack"""
    first = name_slug_part(first_name)
    last = name_slug_part(last_name)
    return f"{str(patient_id).strip()}_{first}_{last}"


def patient_display_name(first_name: str, last_name: str) -> str:
    """Human-readable name for logs, e.g. Paige Pack."""
    return f"{to_pascalcase(first_name)} {to_pascalcase(last_name)}"


def filename_part(text: str) -> str:
    """Replace spaces with underscores for any filename segment."""
    return "_".join((text or "").split())


def details_csv_filename(patient_id, first_name: str, last_name: str) -> str:
    return f"{patient_file_slug(patient_id, first_name, last_name)}_Details.csv"


def patient_image_filename(
    patient_id,
    first_name: str,
    last_name: str,
    image_id: str,
    ext: str,
) -> str:
    """e.g. 227738_Paige_Pack_12345.jpg"""
    first = name_slug_part(first_name)
    last = name_slug_part(last_name)
    pid = str(patient_id).strip()
    if last:
        base = f"{pid}_{first}_{last}_{image_id}"
    else:
        base = f"{pid}_{first}_{image_id}"
    return f"{base}{ext}"
