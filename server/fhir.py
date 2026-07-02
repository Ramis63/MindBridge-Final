"""FHIR R4 mapping for self-reported wellness observations."""
import uuid
from datetime import datetime, timezone

# LOINC / survey codes for student wellness metrics
CODES = {
    'mood': {
        'system': 'http://loinc.org',
        'code': '75258-2',
        'display': 'Mood',
    },
    'energy': {
        'system': 'http://loinc.org',
        'code': '80296-7',
        'display': 'Energy level',
    },
    'stress': {
        'system': 'http://loinc.org',
        'code': '72514-3',
        'display': 'Anxiety score',
    },
    'sleep_duration': {
        'system': 'http://loinc.org',
        'code': '93832-4',
        'display': 'Sleep duration',
    },
    'sleep_quality': {
        'system': 'http://loinc.org',
        'code': '93831-6',
        'display': 'Sleep quality',
    },
}

SLEEP_QUALITY_SCORE = {'Poor': 1, 'Fair': 3, 'Good': 5}


def patient_reference(email: str) -> dict:
    safe_id = email.replace('@', '-at-').replace('.', '-')
    return {
        'resourceType': 'Patient',
        'id': safe_id,
        'identifier': [{
            'system': 'urn:mindbridge:student-email',
            'value': email,
        }],
    }


def _observation(email: str, date: str, metric: str, value, value_type: str) -> dict:
    effective = f'{date}T12:00:00Z'
    obs_id = f'{metric}-{date}-{uuid.uuid4().hex[:8]}'
    resource = {
        'resourceType': 'Observation',
        'id': obs_id,
        'status': 'final',
        'category': [{
            'coding': [{
                'system': 'http://terminology.hl7.org/CodeSystem/observation-category',
                'code': 'survey',
                'display': 'Survey',
            }],
        }],
        'code': {'coding': [CODES[metric]]},
        'subject': {'reference': f'Patient/{email.replace("@", "-at-").replace(".", "-")}'},
        'effectiveDateTime': effective,
        'issued': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    if value_type == 'integer':
        resource['valueInteger'] = int(value)
    elif value_type == 'quantity':
        resource['valueQuantity'] = {
            'value': float(value),
            'unit': 'h',
            'system': 'http://unitsofmeasure.org',
            'code': 'h',
        }
    return resource


def log_to_observations(email: str, log: dict) -> list:
    date = log['date']
    return [
        _observation(email, date, 'mood', log['mood'], 'integer'),
        _observation(email, date, 'energy', log['energy'], 'integer'),
        _observation(email, date, 'stress', log['stress'], 'integer'),
        _observation(email, date, 'sleep_duration', log['sleepHours'], 'quantity'),
        _observation(email, date, 'sleep_quality', SLEEP_QUALITY_SCORE[log['sleepQuality']], 'integer'),
    ]


def logs_to_bundle(email: str, logs: list) -> dict:
    entries = []
    for log in logs:
        for obs in log_to_observations(email, log):
            entries.append({'resource': obs})
    return {
        'resourceType': 'Bundle',
        'type': 'collection',
        'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'entry': entries,
    }


def log_to_questionnaire_response(email: str, log: dict) -> dict:
    """Optional FHIR QuestionnaireResponse for daily check-in survey."""
    return {
        'resourceType': 'QuestionnaireResponse',
        'id': f'qr-{log["date"]}-{uuid.uuid4().hex[:8]}',
        'status': 'completed',
        'subject': {'reference': f'Patient/{email.replace("@", "-at-").replace(".", "-")}'},
        'authored': f'{log["date"]}T20:00:00Z',
        'item': [
            {'linkId': 'mood', 'answer': [{'valueInteger': log['mood']}]},
            {'linkId': 'energy', 'answer': [{'valueInteger': log['energy']}]},
            {'linkId': 'stress', 'answer': [{'valueInteger': log['stress']}]},
            {'linkId': 'sleepHours', 'answer': [{'valueDecimal': log['sleepHours']}]},
            {'linkId': 'sleepQuality', 'answer': [{'valueString': log['sleepQuality']}]},
            {'linkId': 'notes', 'answer': [{'valueString': log.get('notes', '')}]},
        ],
    }


def validate_fhir_observation(observation: dict) -> dict:
    if not isinstance(observation, dict):
        raise ValueError('FHIR observation must be a dictionary')
    if observation.get('resourceType') != 'Observation':
        raise ValueError('FHIR observation must have resourceType Observation')
    if 'id' not in observation:
        raise ValueError('FHIR observation must include an id')
    if 'code' not in observation or 'coding' not in observation['code']:
        raise ValueError('FHIR observation must include a code with coding')
    if 'subject' not in observation or 'reference' not in observation['subject']:
        raise ValueError('FHIR observation must include subject reference')
    if 'effectiveDateTime' not in observation:
        raise ValueError('FHIR observation must include effectiveDateTime')
    if 'issued' not in observation:
        raise ValueError('FHIR observation must include issued timestamp')
    if 'valueInteger' not in observation and 'valueQuantity' not in observation:
        raise ValueError('FHIR observation must contain either valueInteger or valueQuantity')
    return observation


def validate_fhir_bundle(bundle: dict) -> dict:
    if not isinstance(bundle, dict):
        raise ValueError('FHIR bundle must be a dictionary')
    if bundle.get('resourceType') != 'Bundle':
        raise ValueError('FHIR bundle must have resourceType Bundle')
    if bundle.get('type') != 'collection':
        raise ValueError('FHIR bundle must have type collection')
    if not isinstance(bundle.get('entry'), list):
        raise ValueError('FHIR bundle must include entry list')
    for entry in bundle['entry']:
        resource = entry.get('resource')
        if not resource or resource.get('resourceType') != 'Observation':
            raise ValueError('FHIR bundle entries must contain Observation resources')
    return bundle


def validate_fhir_patient(patient: dict) -> dict:
    if not isinstance(patient, dict):
        raise ValueError('FHIR patient must be a dictionary')
    if patient.get('resourceType') != 'Patient':
        raise ValueError('FHIR patient must have resourceType Patient')
    if 'id' not in patient:
        raise ValueError('FHIR patient must include id')
    identifiers = patient.get('identifier')
    if not isinstance(identifiers, list) or not identifiers:
        raise ValueError('FHIR patient must include identifier list')
    return patient
