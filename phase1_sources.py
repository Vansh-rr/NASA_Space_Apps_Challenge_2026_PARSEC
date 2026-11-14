from __future__ import annotations
import os
from dotenv import load_dotenv

# more sources can be added without mutating common schema
SOURCES = {'MODIS_SP': 'modis', 'VIIRS_SNPP_SP': 'viirs'}

def get_map_key() -> str:
    """Reads the SECRET Api key, with read only access"""
    load_dotenv(override=False)
    key = os.getenv('FIRMS_MAP_KEY', '').strip()
    if not key:
        raise RuntimeError(
            'FIRMS_MAP_KEY is missing. Please recheck your key in the secret'
        )
    return key

