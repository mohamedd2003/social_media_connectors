import json
import httpx
from fastapi import HTTPException
from .base import BaseConnector

GRAPH_API = "https://graph.facebook.com/v22.0"


class FacebookConnector(BaseConnector):
    async def get_insights(self, account_id: str, access_token: str):
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(f"{GRAPH_API}/{account_id}/published_posts", params={
                "fields": "id,message,created_time,likes.summary(true),comments.summary(true),shares",
                "access_token": access_token,
                "limit": 50,
            })
            if resp.status_code != 200:
                raise HTTPException(
                    400, f"Failed to fetch FB feed: {resp.text}")

            posts = resp.json().get("data", [])
            results = []

            for post in posts:
                likes = post.get("likes", {}).get(
                    "summary", {}).get("total_count", 0)
                comments = post.get("comments", {}).get(
                    "summary", {}).get("total_count", 0)
                shares = post.get("shares", {}).get("count", 0)

                results.append({
                    "id": post.get("id"),
                    "caption": post.get("message", ""),
                    "created_time": post.get("created_time"),
                    "likes": likes,
                    "comments": comments,
                    "shares": shares,
                    "saves": 0,
                    "impressions": None,
                    "reach": None,
                    "engagement_rate": None,
                    "platform": "facebook",
                })

            for item in results:
                try:
                    resp = await client.get(f"{GRAPH_API}/{item['id']}/insights", params={
                        "metric": "post_impressions,post_impressions_unique",
                        "access_token": access_token,
                    })
                    if resp.status_code == 200:
                        for metric in resp.json().get("data", []):
                            val = metric["values"][0]["value"] if metric.get(
                                "values") else 0
                            if metric["name"] == "post_impressions":
                                item["impressions"] = val
                            elif metric["name"] == "post_impressions_unique":
                                item["reach"] = val

                        numerator = item["likes"] + \
                            item["comments"] + item.get("saves", 0)
                        denominator = item["reach"] or item["impressions"]
                        if denominator:
                            item["engagement_rate"] = round(
                                (numerator / denominator) * 100, 2)
                except Exception:
                    pass

            return results

    async def publish_post(self, account_id: str, access_token: str, message: str, images: list = None, **kwargs):
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Clean up the list to filter out None or empty uploads
            valid_images = []
            if images:
                valid_images = [img for img in images if img and img.filename]

            if not valid_images:
                # Text-only post
                resp = await client.post(f"{GRAPH_API}/{account_id}/feed", data={
                    "message": message,
                    "access_token": access_token
                })
            elif len(valid_images) == 1:
                # Single photo post
                image = valid_images[0]
                image_data = await image.read()
                files = {
                    "source": (image.filename, image_data, image.content_type)
                }
                data = {
                    "message": message,
                    "access_token": access_token
                }
                resp = await client.post(f"{GRAPH_API}/{account_id}/photos", data=data, files=files)
            else:
                # Multiple photos post: upload as unpublished, then attach to a feed post
                photo_ids = []
                for image in valid_images:
                    image_data = await image.read()
                    files = {
                        "source": (image.filename, image_data, image.content_type)
                    }
                    data = {
                        "published": "false",
                        "access_token": access_token
                    }
                    photo_resp = await client.post(f"{GRAPH_API}/{account_id}/photos", data=data, files=files)
                    if photo_resp.status_code != 200:
                        raise HTTPException(photo_resp.status_code, f"Failed to upload image {image.filename}: {photo_resp.text}")
                    
                    photo_id = photo_resp.json().get("id")
                    if photo_id:
                        photo_ids.append(photo_id)
                
                # Now attach the photos to a feed post
                attached_media = [{"media_fbid": pid} for pid in photo_ids]
                feed_data = {
                    "message": message,
                    "attached_media": json.dumps(attached_media),
                    "access_token": access_token
                }
                resp = await client.post(f"{GRAPH_API}/{account_id}/feed", data=feed_data)
            
            if resp.status_code != 200:
                raise HTTPException(400, f"Failed to publish post: {resp.text}")
                
            return resp.json()

    async def get_comments(self, post_id: str, access_token: str):
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(f"{GRAPH_API}/{post_id}/comments", params={
                "fields": "id,message,created_time,from",
                "access_token": access_token,
                "limit": 50,
            })
            if resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch FB comments: {resp.text}")
            
            comments = resp.json().get("data", [])
            results = []
            for c in comments:
                author_name = c.get("from", {}).get("name", "Unknown")
                results.append({
                    "id": c.get("id"),
                    "text": c.get("message", ""),
                    "author": author_name,
                    "timestamp": c.get("created_time")
                })
            return results
