"""Wildberries API integration service."""

import requests
import time
from typing import List, Dict, Optional


class WildberriesAPI:
    """Service for interacting with Wildberries Content API."""

    BASE_URL = "https://content-api.wildberries.ru"

    def __init__(self, api_key: str):
        """Initialize with API key."""
        self.api_key = api_key
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }

    def fetch_all_products(
        self,
        with_photo: int = -1,
        limit: int = 100,
        max_pages: Optional[int] = None
    ) -> tuple[List[Dict], int]:
        """
        Fetch all products from WB API.

        Args:
            with_photo: Filter by photo (-1 = all, 0 = without photo, 1 = with photo)
            limit: Number of products per page
            max_pages: Maximum number of pages to fetch (None = all)

        Returns:
            Tuple of (list of cards, number of pages fetched)
        """
        url = f"{self.BASE_URL}/content/v2/get/cards/list"

        all_cards = []
        cursor = {"limit": limit}
        pages = 0

        max_retries = 4
        backoff_base = 0.6

        while True:
            payload = {
                "settings": {
                    "filter": {"withPhoto": with_photo},
                    "cursor": cursor
                }
            }

            data = None
            for attempt in range(max_retries + 1):
                try:
                    resp = requests.post(url, headers=self.headers, json=payload, timeout=60)
                    status = resp.status_code

                    if status == 401:
                        raise Exception("API ключ недействителен или истёк (401).")

                    if status in (429, 500, 502, 503, 504):
                        time.sleep(backoff_base * (2 ** attempt))
                        continue

                    if status != 200:
                        raise Exception(f"Ошибка запроса WB: {status} {resp.text[:300]}")

                    data = resp.json()
                    break

                except Exception as e:
                    if attempt >= max_retries:
                        raise
                    time.sleep(backoff_base * (2 ** attempt))

            cards = (data or {}).get("cards", []) or []
            if not cards:
                break

            all_cards.extend(cards)
            pages += 1

            new_cursor = (data or {}).get("cursor") or {}
            if not new_cursor.get("updatedAt") or not new_cursor.get("nmID"):
                break

            cursor = {
                "limit": limit,
                "updatedAt": new_cursor["updatedAt"],
                "nmID": new_cursor["nmID"]
            }

            if max_pages and pages >= max_pages:
                break

            time.sleep(0.12)  # Rate limiting

        return all_cards, pages

    def get_product_by_nmid(self, nm_id: int) -> Optional[Dict]:
        """
        Get product card by nmID.

        Args:
            nm_id: Product nmID

        Returns:
            Product card dict or None if not found
        """
        # Since WB API doesn't have a direct endpoint for getting a single product by nmID,
        # we need to fetch all products and filter
        # For better performance, we'll fetch with pagination and stop when found

        url = f"{self.BASE_URL}/content/v2/get/cards/list"
        cursor = {"limit": 100}
        max_retries = 4
        backoff_base = 0.6

        while True:
            payload = {
                "settings": {
                    "filter": {"withPhoto": -1},
                    "cursor": cursor
                }
            }

            data = None
            for attempt in range(max_retries + 1):
                try:
                    resp = requests.post(url, headers=self.headers, json=payload, timeout=60)
                    status = resp.status_code

                    if status == 401:
                        raise Exception("API ключ недействителен или истёк (401).")

                    if status in (429, 500, 502, 503, 504):
                        time.sleep(backoff_base * (2 ** attempt))
                        continue

                    if status != 200:
                        raise Exception(f"Ошибка запроса WB: {status} {resp.text[:300]}")

                    data = resp.json()
                    break

                except Exception as e:
                    if attempt >= max_retries:
                        raise
                    time.sleep(backoff_base * (2 ** attempt))

            cards = (data or {}).get("cards", []) or []

            # Search for the product in current batch
            for card in cards:
                if card.get("nmID") == nm_id:
                    return card

            # Check if there are more pages
            new_cursor = (data or {}).get("cursor") or {}
            if not new_cursor.get("updatedAt") or not new_cursor.get("nmID"):
                break

            cursor = {
                "limit": 100,
                "updatedAt": new_cursor["updatedAt"],
                "nmID": new_cursor["nmID"]
            }

            time.sleep(0.12)  # Rate limiting

        return None

    def get_products_by_nmids(self, nm_ids: List[int]) -> Dict[int, Optional[Dict]]:
        """
        Get multiple products by their nmIDs.

        Args:
            nm_ids: List of nmIDs

        Returns:
            Dict mapping nmID to product card (or None if not found)
        """
        nm_ids_set = set(nm_ids)
        results = {nm_id: None for nm_id in nm_ids}

        url = f"{self.BASE_URL}/content/v2/get/cards/list"
        cursor = {"limit": 100}
        max_retries = 4
        backoff_base = 0.6

        while True:
            payload = {
                "settings": {
                    "filter": {"withPhoto": -1},
                    "cursor": cursor
                }
            }

            data = None
            for attempt in range(max_retries + 1):
                try:
                    resp = requests.post(url, headers=self.headers, json=payload, timeout=60)
                    status = resp.status_code

                    if status == 401:
                        raise Exception("API ключ недействителен или истёк (401).")

                    if status in (429, 500, 502, 503, 504):
                        time.sleep(backoff_base * (2 ** attempt))
                        continue

                    if status != 200:
                        raise Exception(f"Ошибка запроса WB: {status} {resp.text[:300]}")

                    data = resp.json()
                    break

                except Exception as e:
                    if attempt >= max_retries:
                        raise
                    time.sleep(backoff_base * (2 ** attempt))

            cards = (data or {}).get("cards", []) or []

            # Search for products in current batch
            for card in cards:
                nm_id = card.get("nmID")
                if nm_id in nm_ids_set:
                    results[nm_id] = card
                    nm_ids_set.remove(nm_id)

            # If all products found, stop
            if not nm_ids_set:
                break

            # Check if there are more pages
            new_cursor = (data or {}).get("cursor") or {}
            if not new_cursor.get("updatedAt") or not new_cursor.get("nmID"):
                break

            cursor = {
                "limit": 100,
                "updatedAt": new_cursor["updatedAt"],
                "nmID": new_cursor["nmID"]
            }

            time.sleep(0.12)  # Rate limiting

        return results
