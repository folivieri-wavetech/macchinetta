"""
Sistema/fuso_orario.py - Gestione centralizzata e automatica del fuso orario italiano (Europe/Rome).
Supporta in modo 100% automatico il passaggio tra Ora Solare (CET, UTC+1) e Ora Legale (CEST, UTC+2).
Non richiede interventi manuali e include fallback dinamico basato sulle regole ufficiali UE
se la libreria o il database tzdata di sistema non fossero presenti nell'ambiente Linux/container.
"""
import datetime
from datetime import timezone, timedelta

class DynamicItalianTimeZone(datetime.tzinfo):
    """
    Fuso orario italiano con calcolo dinamico dell'ora legale/solare (regole standard UE).
    - Ora Legale (CEST, UTC+2): dall'ultima domenica di marzo alle 01:00 UTC
    - Ora Solare (CET, UTC+1): dall'ultima domenica di ottobre alle 01:00 UTC
    """
    def utcoffset(self, dt):
        return timedelta(hours=2 if self._is_dst(dt) else 1)

    def dst(self, dt):
        return timedelta(hours=1 if self._is_dst(dt) else 0)

    def tzname(self, dt):
        return "CEST" if self._is_dst(dt) else "CET"

    def _is_dst(self, dt):
        if dt is None:
            return False
        if dt.tzinfo is not None and dt.tzinfo != self:
            dt_utc = dt.astimezone(timezone.utc)
        elif dt.tzinfo == self:
            dt_utc = (dt - timedelta(hours=1)).replace(tzinfo=timezone.utc)
        else:
            dt_utc = dt.replace(tzinfo=timezone.utc)

        y = dt_utc.year
        # Ultima domenica di marzo alle 01:00 UTC
        last_sun_mar = 31 - ((datetime.date(y, 3, 31).weekday() + 1) % 7)
        dst_start = datetime.datetime(y, 3, last_sun_mar, 1, 0, tzinfo=timezone.utc)
        # Ultima domenica di ottobre alle 01:00 UTC
        last_sun_oct = 31 - ((datetime.date(y, 10, 31).weekday() + 1) % 7)
        dst_end = datetime.datetime(y, 10, last_sun_oct, 1, 0, tzinfo=timezone.utc)
        return dst_start <= dt_utc < dst_end

try:
    from zoneinfo import ZoneInfo
    # Test if Europe/Rome is actually available and working in the tz database
    _tz_candidate = ZoneInfo("Europe/Rome")
    _tz_candidate.utcoffset(datetime.datetime.now(timezone.utc))
    TZ_ITALIA = _tz_candidate
except Exception:
    TZ_ITALIA = DynamicItalianTimeZone()

def now_it() -> datetime.datetime:
    """Ritorna il datetime corrente nel fuso orario di Roma (automaticamente UTC+1 o UTC+2)."""
    return datetime.datetime.now(TZ_ITALIA)
