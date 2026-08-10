"""Party presentation metadata: main colour + actual uploaded logo image.

The platform stays data-driven - parties come from uploaded data. This module
only decides how a party is *presented* (colour / logo). Known national and
regional parties get their well-known colour and the ACTUAL uploaded logo file
from static/images/parties/; any other party that an Admin uploads gets a
stable colour from the fallback palette and a generic initials badge rendered
on the client.

IMPORTANT: no emojis / Unicode symbols are ever used as party symbols.
"""

import hashlib
import os
from urllib.parse import quote

# Fallback palette for parties that are not in PARTY_META
FALLBACK_COLORS = [
    '#0891b2', '#7c3aed', '#db2777', '#0ea5e9', '#65a30d', '#f97316',
    '#64748b', '#0f766e', '#a21caf', '#eab308', '#2563eb', '#e11d48',
]

# key: normalised party name/abbreviation -> main colour
PARTY_META = {
    'BJP': '#FF9933',
    'BHARATIYA JANATA PARTY': '#FF9933',
    'INC': '#19AAED',
    'CONGRESS': '#19AAED',
    'INDIAN NATIONAL CONGRESS': '#19AAED',
    'SP': '#E4002B',
    'SAMAJWADI PARTY': '#E4002B',
    'BSP': '#22409A',
    'BAHUJAN SAMAJ PARTY': '#22409A',
    'AAP': '#0078AE',
    'AAM AADMI PARTY': '#0078AE',
    'TMC': '#17B44B',
    'AITC': '#17B44B',
    'ALL INDIA TRINAMOOL CONGRESS': '#17B44B',
    'DMK': '#D40000',
    'DRAVIDA MUNNETRA KAZHAGAM': '#D40000',
    'AIADMK': '#008000',
    'SHS': '#FF6600',
    'SHIV SENA': '#FF6600',
    'NCP': '#0057A0',
    'JD(U)': '#00B140',
    'JDU': '#00B140',
    'CPI(M)': '#CC0000',
    'CPM': '#CC0000',
    'CPI': '#CC0000',
    'BJD': '#008000',
    'TDP': '#FFD700',
    'YSRCP': '#006666',
    'RJD': '#00712D',
    'JMM': '#1E90FF',
    'JHARKHAND MUKTI MORCHA': '#1E90FF',
    'BRS': '#F288B0',
    'TRS': '#F288B0',
    'RLD': '#0066CC',
    'RASHTRIYA LOK DAL': '#0066CC',
    'INLD': '#0066CC',
    'IND': '#64748b',
    'NOTA': '#94a3b8',
}

# ------------------------------------------------------------------
# CENTRAL PARTY-LOGO MAPPING (actual uploaded image files only)
# key: normalised party abbreviation -> exact file in static/images/parties/
PARTY_LOGOS = {
    'AAP': 'AAP.jpg',
    'BSP': 'bahujan_samaj_party_logo.jpg',
    'BJP': 'BJP ICON main.jpg',
    'DMK': 'DMK.jpg',
    'INC': 'INC.jpg',
    'JMM': 'JMM.jpg',
    'RLD': 'rashtriya-lok-dal.webp',
    'SP': 'Samajwadi Party Icon.webp',
    'TMC': 'TMC.jpg',
}

# Full dataset names that should resolve to the same logo
LOGO_ALIASES = {
    'AAM AADMI PARTY': 'AAP',
    'BAHUJAN SAMAJ PARTY': 'BSP',
    'BHARATIYA JANATA PARTY': 'BJP',
    'DRAVIDA MUNNETRA KAZHAGAM': 'DMK',
    'INDIAN NATIONAL CONGRESS': 'INC',
    'CONGRESS': 'INC',
    'JHARKHAND MUKTI MORCHA': 'JMM',
    'RASHTRIYA LOK DAL': 'RLD',
    'SAMAJWADI PARTY': 'SP',
    'AITC': 'TMC',
    'ALL INDIA TRINAMOOL CONGRESS': 'TMC',
    'TRINAMOOL CONGRESS': 'TMC',
}

LOGO_DIR = os.path.join('images', 'parties')


def _normalise(name):
    return str(name or '').strip().upper()


def _stable_index(key):
    """Process-stable index (Python's hash() is salted per run)."""
    return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)


def party_color(name):
    """Main colour for a party; stable fallback colour for unknown parties."""
    key = _normalise(name)
    if key in PARTY_META:
        return PARTY_META[key]
    for known in PARTY_META:
        if key.startswith(known + ' ') or key.startswith(known + '('):
            return PARTY_META[known]
    return FALLBACK_COLORS[_stable_index(key) % len(FALLBACK_COLORS)]


def party_logo(name):
    """URL of the actual uploaded logo image for a party; None for parties
    without a logo file (client renders a coloured initials badge instead)."""
    key = _normalise(name)
    abbr = LOGO_ALIASES.get(key, key)
    filename = PARTY_LOGOS.get(abbr)
    if not filename:
        # allow long dataset names like "BJP - BHARATIYA JANATA ..."
        for known, a in LOGO_ALIASES.items():
            if key.startswith(known + ' ') or key.startswith(known + '('):
                filename = PARTY_LOGOS.get(a)
                break
        else:
            for known in PARTY_LOGOS:
                if key.startswith(known + ' ') or key.startswith(known + '('):
                    filename = PARTY_LOGOS.get(known)
                    break
    if not filename:
        return None
    return '/static/' + quote(f'{LOGO_DIR}/{filename}'.replace(os.sep, '/'))


def party_meta(name):
    return {'color': party_color(name), 'logo': party_logo(name)}
