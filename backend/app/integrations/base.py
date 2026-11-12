"""Phase 3 seam for marketplace order import.

Shopee, Lazada, TikTok Shop, and Shopify are not connected.
An adapter would pull remote orders and hand them to the order service,
which is the only path that reserves stock.
"""

from typing import Protocol
from uuid import UUID


class MarketplaceAdapter(Protocol):
    name: str

    def pull_orders(self, customer_id: UUID) -> list[dict]:
        """Return order payloads. Must not write inventory itself."""
