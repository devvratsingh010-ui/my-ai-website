"""Product catalog alias resolution and business category defaults."""

import re
from typing import Any, Dict, List, Optional


class ProductCatalogMatcher:
    """Matches raw item names against shop aliases and standard catalog."""

    def __init__(self, shop_aliases: Optional[List[Dict[str, Any]]] = None):
        self.aliases = shop_aliases or []

    def find_match(self, raw_item_name: str) -> Optional[Dict[str, Any]]:
        """Find standardized product name for a raw item text if an alias exists.

        Does NOT translate; returns standardized category name while leaving original text intact.
        """
        if not raw_item_name:
            return None

        clean_name = raw_item_name.strip().lower()

        for alias in self.aliases:
            alias_name = alias.get("alias_name", "").strip().lower()
            if not alias_name:
                continue

            # Exact match or word boundary match
            if clean_name == alias_name or clean_name.startswith(alias_name + " ") or clean_name.endswith(" " + alias_name):
                return {
                    "standard_name": alias.get("standard_name"),
                    "matched_alias": alias.get("alias_name"),
                    "language_code": alias.get("language_code"),
                    "default_unit": alias.get("default_unit"),
                    "default_price": alias.get("default_price"),
                }

        return None
