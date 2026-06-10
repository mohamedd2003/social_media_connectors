from abc import ABC, abstractmethod

class BaseConnector(ABC):
    """Abstract base class for all social media connectors."""

    @abstractmethod
    async def get_insights(self, account_id: str, access_token: str):
        """Fetch insights/posts for the given account."""
        pass

    @abstractmethod
    async def publish_post(self, account_id: str, access_token: str, message: str, images: list = None, **kwargs):
        """Publish a post to the given account."""
        pass

    @abstractmethod
    async def get_comments(self, post_id: str, access_token: str):
        """Fetch comments for a specific post."""
        pass
