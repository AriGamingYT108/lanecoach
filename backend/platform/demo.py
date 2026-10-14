"""Anonymous visitor isolation and finite, database-backed public AI request budgets."""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from fastapi import HTTPException

COOKIE = 'lanecoach_visitor'


class Demo:
    def __init__(self):
        self.public = os.getenv('APP_ENV') == 'production' or bool(os.getenv('RAILWAY_ENVIRONMENT_ID'))
        self.secret = os.getenv('APP_SECRET', '')
        self.proxy_token = os.getenv('INTERNAL_PROXY_TOKEN', '')
        if self.public and (len(self.secret) < 32 or len(self.proxy_token) < 32 or not os.getenv('FRONTEND_ORIGIN', '').startswith('https://')):
            raise RuntimeError('Production requires APP_SECRET, INTERNAL_PROXY_TOKEN and an HTTPS FRONTEND_ORIGIN.')
        self.secret = self.secret or secrets.token_hex(32)
        self.daily = int(os.getenv('AI_DAILY_REQUEST_LIMIT', '100'))
        self.visitor_daily = int(os.getenv('AI_VISITOR_DAILY_LIMIT', '10'))
        self.visitor_minute = int(os.getenv('AI_VISITOR_MINUTE_LIMIT', '3'))
        if min(self.daily, self.visitor_daily, self.visitor_minute) < 0:
            raise RuntimeError('AI request limits must be nonnegative.')

    def sign(self, value):
        return hmac.new(self.secret.encode(), value.encode(), hashlib.sha256).hexdigest()

    def visitor(self, cookie):
        if not cookie:
            return None
        identifier, separator, signature = cookie.partition('.')
        if not separator or len(identifier) != 64 or not hmac.compare_digest(signature, self.sign(identifier)):
            return None
        return self.sign('owner:' + identifier)

    def create_cookie(self):
        identifier = secrets.token_hex(32)
        return identifier + '.' + self.sign(identifier)

    def owner(self, request, csrf=False):
        if not self.public:
            return None
        owner = self.visitor(request.cookies.get(COOKIE))
        if not owner:
            raise HTTPException(403, 'Reload LaneCoach to initialize your private demo conversation.')
        if csrf and not hmac.compare_digest(request.headers.get('x-lanecoach-csrf', ''), self.sign('csrf:' + owner)):
            raise HTTPException(403, 'Reload LaneCoach and try again.')
        return owner

    def reserve(self, store, owner):
        if not self.public:
            return
        now = datetime.now(timezone.utc)
        limits = {'global:' + now.strftime('%Y-%m-%d'): self.daily,
                  'visitor:' + owner + ':' + now.strftime('%Y-%m-%d'): self.visitor_daily,
                  'minute:' + owner + ':' + now.strftime('%Y-%m-%dT%H:%M'): self.visitor_minute}
        if not store.reserve_requests(limits):
            raise HTTPException(429, 'The coaching demo has reached a request limit. Try later; stored answers and evidence remain available.')
