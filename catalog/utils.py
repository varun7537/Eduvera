from django.core import signing
from django.conf import settings

def make_video_token(user_id, lesson_id):
    payload = {'u': user_id, 'l': lesson_id}
    # use default signer; we'll enforce max_age when loading
    return signing.dumps(payload)

def load_video_token(token, max_age=None):
    if max_age is None:
        max_age = getattr(settings, 'VIDEO_TOKEN_MAX_AGE', 1800)
    try:
        data = signing.loads(token, max_age=max_age)
        return data  # dict with 'u' and 'l'
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None
