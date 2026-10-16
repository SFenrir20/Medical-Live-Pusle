"""The TikTokers and the code each one writes in the live title.

`name` is the name used in reports ("Nombre usado"); `full_name` is kept for reference.
Applied by migration 0008 and safe to run again (it updates by id, never duplicates)."""
from datetime import datetime, timezone

from sqlalchemy import text

ROSTER = [
    {'id': 'TK-A01', 'code': 'A1', 'name': 'Ash', 'full_name': 'Ashley'},
    {'id': 'TK-M02', 'code': 'M2', 'name': 'Mari', 'full_name': 'Maria Luisa'},
    {'id': 'TK-L03', 'code': 'L3', 'name': 'Lu', 'full_name': 'Lucía'},
    {'id': 'TK-B04', 'code': 'B4', 'name': 'Bri', 'full_name': 'Briggite'},
    {'id': 'TK-F05', 'code': 'F5', 'name': 'Fer', 'full_name': 'Fernanda'},
    {'id': 'TK-N06', 'code': 'N6', 'name': 'Nahit', 'full_name': 'Nahit'},
]


def seed_roster(conn) -> int:
    """Insert or refresh the roster (portable SQL). Returns how many rows were created."""
    now = datetime.now(timezone.utc)
    created = 0
    for row in ROSTER:
        exists = conn.execute(text('SELECT 1 FROM tiktokers WHERE id = :id'), row).first()
        if exists:
            conn.execute(text(
                'UPDATE tiktokers SET name = :name, code = :code, full_name = :full_name, '
                'active = :active WHERE id = :id'), {**row, 'active': True})
        else:
            conn.execute(text(
                'INSERT INTO tiktokers (id, name, code, full_name, active, created_at) '
                'VALUES (:id, :name, :code, :full_name, :active, :now)'),
                {**row, 'active': True, 'now': now})
            created += 1
    return created
