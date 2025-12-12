"""One-off repair script to ensure `gifts` has a room_id column.

Usage:
    python scripts/repair_gifts_room_id.py --env-file .env

This forces a rebuild of the gifts table while preserving compatible data
columns. If the table already has room_id, it is left unchanged.
"""

from __future__ import annotations

import argparse

from config.settings import get_settings
from db.sqlite import _force_recreate_gifts, _guarantee_gifts_room_id, get_conn


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair gifts table room_id column")
    parser.add_argument("--env-file", "--env_file", "-e", help="Path to .env file", default=None)
    args = parser.parse_args()

    settings = get_settings(env_file=args.env_file)
    with get_conn(settings) as conn:
        ensured = _guarantee_gifts_room_id(conn)
        if ensured:
            print("room_id already present; no action needed")
            return

        print("room_id missing; rebuilding gifts table and retrying ensure")
        _force_recreate_gifts(conn)
        conn.commit()
        if _guarantee_gifts_room_id(conn):
            print("room_id repair completed successfully")
        else:
            print("room_id repair failed; please inspect the database manually")


if __name__ == "__main__":
    main()
