"""
fuso_orario.py - Re-export di Sistema.fuso_orario per moduli root.
"""
try:
    from Sistema.fuso_orario import DynamicItalianTimeZone, TZ_ITALIA, now_it
except ImportError:
    from fuso_orario import DynamicItalianTimeZone, TZ_ITALIA, now_it
