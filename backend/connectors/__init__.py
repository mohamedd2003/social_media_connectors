from .base import BaseConnector
from .facebook import FacebookConnector
from .instagram import InstagramConnector
from .snapchat import SnapchatConnector

# Registry mapping account types to their respective connector instances
_connectors = {
    "facebook_page": FacebookConnector(),
    "instagram": InstagramConnector(),
    "snapchat": SnapchatConnector(),
}

def get_connector(account_type: str) -> BaseConnector:
    """Returns the appropriate connector for the given account type."""
    connector = _connectors.get(account_type)
    if not connector:
        raise ValueError(f"No connector found for account type: {account_type}")
    return connector
