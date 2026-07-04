"""Input validation for wellness logs and auth payloads."""
import re
from datetime import datetime

EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
SLEEP_QUALITIES = frozenset({'Poor', 'Fair', 'Good'})
MAX_NOTES_LEN = 2000
MAX_TAG_LEN = 40
MAX_TAGS = 10


class ValidationError(Exception):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field
        self.message = message


def validate_email(email: str) -> str:
    email = (email or '').strip().lower()
    if not EMAIL_RE.match(email):
        raise ValidationError('Invalid email address', 'email')
    return email


def validate_password(password: str) -> str:
    if not password or len(password) < 6:
        raise ValidationError('Password must be at least 6 characters', 'password')
    if len(password) > 128:
        raise ValidationError('Password is too long', 'password')
    return password


def validate_name(name: str, field: str) -> str:
    name = (name or '').strip()
    if not name or len(name) > 80:
        raise ValidationError(f'Invalid {field}', field)
    return name


def validate_log_entry(entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise ValidationError('Log entry must be a JSON object')

    date = entry.get('date', '')
    if not DATE_RE.match(str(date)):
        raise ValidationError('Date must be YYYY-MM-DD', 'date')
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError as exc:
        raise ValidationError('Invalid calendar date', 'date') from exc

    mood = entry.get('mood')
    energy = entry.get('energy')
    stress = entry.get('stress')
    for field, value in (('mood', mood), ('energy', energy), ('stress', stress)):
        if not isinstance(value, int) or value < 1 or value > 5:
            raise ValidationError(f'{field} must be an integer from 1 to 5', field)

    sleep_hours = entry.get('sleepHours')
    if not isinstance(sleep_hours, (int, float)) or sleep_hours < 0 or sleep_hours > 16:
        raise ValidationError('sleepHours must be between 0 and 16', 'sleepHours')

    sleep_quality = entry.get('sleepQuality')
    if sleep_quality not in SLEEP_QUALITIES:
        raise ValidationError('sleepQuality must be Poor, Fair, or Good', 'sleepQuality')

    notes = entry.get('notes', '') or ''
    if not isinstance(notes, str) or len(notes) > MAX_NOTES_LEN:
        raise ValidationError(f'notes must be at most {MAX_NOTES_LEN} characters', 'notes')

    tags = entry.get('tags', []) or []
    if not isinstance(tags, list) or len(tags) > MAX_TAGS:
        raise ValidationError(f'tags must be a list with at most {MAX_TAGS} items', 'tags')
    clean_tags = []
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip() or len(tag) > MAX_TAG_LEN:
            raise ValidationError('Each tag must be a non-empty string', 'tags')
        clean_tags.append(tag.strip())

    return {
        'date': date,
        'mood': mood,
        'energy': energy,
        'sleepHours': float(sleep_hours),
        'sleepQuality': sleep_quality,
        'stress': stress,
        'notes': notes,
        'tags': clean_tags,
    }


def validate_settings(settings: dict) -> dict:
    if not isinstance(settings, dict):
        raise ValidationError('Settings must be a JSON object', 'settings')

    theme = settings.get('theme', 'light')
    if theme not in {'light', 'dark'}:
        raise ValidationError('theme must be light or dark', 'theme')

    anonymous_sharing = settings.get('anonymousSharing', False)
    if not isinstance(anonymous_sharing, bool):
        raise ValidationError('anonymousSharing must be a boolean', 'anonymousSharing')

    onboarded = settings.get('onboarded', False)
    if not isinstance(onboarded, bool):
        raise ValidationError('onboarded must be a boolean', 'onboarded')

    goals = settings.get('goals', [])
    if not isinstance(goals, list) or not all(isinstance(g, str) for g in goals):
        raise ValidationError('goals must be a list of strings', 'goals')

    reminder_time = settings.get('reminderTime', 'evening')
    if not isinstance(reminder_time, str):
        raise ValidationError('reminderTime must be a string', 'reminderTime')

    return {
        'theme': theme,
        'anonymousSharing': anonymous_sharing,
        'onboarded': onboarded,
        'goals': goals,
        'reminderTime': reminder_time,
    }
