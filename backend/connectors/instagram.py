import os
import uuid
import httpx
import aiofiles
from fastapi import HTTPException
from .base import BaseConnector

GRAPH_API = "https://graph.facebook.com/v22.0"


class InstagramConnector(BaseConnector):
    async def get_insights(self, account_id: str, access_token: str):
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(f"{GRAPH_API}/{account_id}/media", params={
                "fields": "id,caption,media_type,timestamp,like_count,comments_count",
                "access_token": access_token,
                "limit": 50,
            })
            if resp.status_code != 200:
                raise HTTPException(
                    400, f"Failed to fetch IG media: {resp.text}")

            media_list = resp.json().get("data", [])
            results = []

            for media in media_list:
                media_id = media["id"]
                media_type = media.get("media_type", "IMAGE")
                likes = media.get("like_count", 0)
                comments = media.get("comments_count", 0)

                if media_type == "VIDEO" or media_type == "REEL":
                    metrics = "impressions,reach,saved,video_views"
                else:
                    metrics = "impressions,reach,saved"

                impressions = 0
                reach = 0
                saves = 0

                try:
                    insight_resp = await client.get(f"{GRAPH_API}/{media_id}/insights", params={
                        "metric": metrics,
                        "access_token": access_token,
                    })
                    if insight_resp.status_code == 200:
                        for m in insight_resp.json().get("data", []):
                            val = m["values"][0]["value"] if m.get(
                                "values") else 0
                            if m["name"] == "impressions":
                                impressions = val
                            elif m["name"] == "reach":
                                reach = val
                            elif m["name"] == "saved":
                                saves = val
                except Exception:
                    pass

                numerator = likes + comments + saves
                denominator = reach or impressions
                engagement_rate = round(
                    (numerator / denominator) * 100, 2) if denominator else None

                results.append({
                    "id": media_id,
                    "caption": media.get("caption", ""),
                    "created_time": media.get("timestamp"),
                    "media_type": media_type,
                    "likes": likes,
                    "comments": comments,
                    "shares": 0,
                    "saves": saves,
                    "impressions": impressions,
                    "reach": reach,
                    "engagement_rate": engagement_rate,
                    "platform": "instagram",
                })

            return results

    async def publish_post(self, account_id: str, access_token: str, message: str, images: list = None, **kwargs):
        base_url = kwargs.get("base_url", "http://localhost:8000/")
        if not base_url.endswith("/"):
            base_url += "/"

        valid_images = [img for img in (images or []) if img and img.filename]
        if not valid_images:
            raise HTTPException(
                400, "Instagram posts require at least one image.")

        # Save images locally
        image_urls = []
        saved_filepaths = []
        for image in valid_images:
            ext = os.path.splitext(image.filename)[1]
            filename = f"{uuid.uuid4().hex}{ext}"
            filepath = os.path.join("static", "uploads", filename)

            async with aiofiles.open(filepath, 'wb') as out_file:
                content = await image.read()
                await out_file.write(content)

            saved_filepaths.append(filepath)
            image_urls.append(f"{base_url}static/uploads/{filename}")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                if len(image_urls) == 1:
                    # Single Image Post
                    # Step 1: Create media container
                    media_data = {
                        "image_url": image_urls[0],
                        "caption": message,
                        "access_token": access_token
                    }
                    resp = await client.post(f"{GRAPH_API}/{account_id}/media", data=media_data)
                    if resp.status_code != 200:
                        raise HTTPException(
                            400, f"Failed to create IG media: {resp.text}")

                    creation_id = resp.json().get("id")

                    # Step 2: Publish media container
                    pub_data = {
                        "creation_id": creation_id,
                        "access_token": access_token
                    }
                    pub_resp = await client.post(f"{GRAPH_API}/{account_id}/media_publish", data=pub_data)
                    if pub_resp.status_code != 200:
                        raise HTTPException(
                            400, f"Failed to publish IG media: {pub_resp.text}")

                    return pub_resp.json()
                else:
                    # Carousel Post
                    # Step 1: Create carousel items
                    item_ids = []
                    for img_url in image_urls:
                        item_data = {
                            "image_url": img_url,
                            "is_carousel_item": "true",
                            "access_token": access_token
                        }
                        resp = await client.post(f"{GRAPH_API}/{account_id}/media", data=item_data)
                        if resp.status_code != 200:
                            raise HTTPException(
                                400, f"Failed to create IG carousel item: {resp.text}")
                        item_ids.append(resp.json().get("id"))

                    # Step 2: Create carousel container
                    carousel_data = {
                        "media_type": "CAROUSEL",
                        "caption": message,
                        "children": ",".join(item_ids),
                        "access_token": access_token
                    }
                    c_resp = await client.post(f"{GRAPH_API}/{account_id}/media", data=carousel_data)
                    if c_resp.status_code != 200:
                        raise HTTPException(
                            400, f"Failed to create IG carousel container: {c_resp.text}")

                    creation_id = c_resp.json().get("id")

                    # Step 3: Publish carousel container
                    pub_data = {
                        "creation_id": creation_id,
                        "access_token": access_token
                    }
                    pub_resp = await client.post(f"{GRAPH_API}/{account_id}/media_publish", data=pub_data)
                    if pub_resp.status_code != 200:
                        raise HTTPException(
                            400, f"Failed to publish IG carousel: {pub_resp.text}")

                    return pub_resp.json()
        finally:
            # Clean up uploaded files after publish attempt
            for fp in saved_filepaths:
                try:
                    os.remove(fp)
                except OSError:
                    pass

    async def get_comments(self, post_id: str, access_token: str):
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(f"{GRAPH_API}/{post_id}/comments", params={
                "fields": "id,text,timestamp,username",
                "access_token": access_token,
                "limit": 50,
            })
            if resp.status_code != 200:
                raise HTTPException(
                    400, f"Failed to fetch IG comments: {resp.text}")

            comments = resp.json().get("data", [])
            results = []
            for c in comments:
                results.append({
                    "id": c.get("id"),
                    "text": c.get("text", ""),
                    "author": c.get("username", "Unknown"),
                    "timestamp": c.get("timestamp")
                })
            return results
