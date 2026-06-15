import { useState, useEffect, useCallback, useRef } from "react";

/**
 * TikTokDashboard – Modern TikTok integration dashboard with three tabs:
 * - Analytics: Profile overview + metric cards (Followers, Views, Engagement)
 * - Videos: Grid of recent videos with per-video stats
 * - Publish: Drag-and-drop video URL picker + caption editor + post button
 */
export default function TikTokDashboard({ accountId, backendUrl = "" }) {
  // ─── State ──────────────────────────────────────────────────────────
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("analytics");

  // Analytics data
  const [analytics, setAnalytics] = useState(null);
  const [needsReauth, setNeedsReauth] = useState(false);

  // Publish form state
  const [videoUrl, setVideoUrl] = useState("");
  const [videoFile, setVideoFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState("");
  const [caption, setCaption] = useState("");
  const [privacyLevel, setPrivacyLevel] = useState("SELF_ONLY");
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishStatus, setPublishStatus] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  // ─── Fetch analytics data ──────────────────────────────────────────

  const fetchAnalytics = useCallback(async () => {
    if (!accountId) return;
    setLoading(true);
    setError(null);
    setNeedsReauth(false);
    try {
      const res = await fetch(
        `${backendUrl}/tiktok/profile/analytics?account_id=${accountId}`
      );
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 401) {
          setNeedsReauth(true);
          throw new Error(data.detail || "TikTok session expired.");
        }
        throw new Error(data.detail || "Failed to load TikTok analytics");
      }
      setAnalytics(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [accountId, backendUrl]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  // ─── Publish handler ──────────────────────────────────────────────

  const handlePublish = async (e) => {
    e.preventDefault();
    if (!caption.trim()) {
      setPublishStatus({ type: "error", message: "Please add a caption before posting." });
      return;
    }
    if (!videoUrl.trim() && !videoFile) return;

    setIsPublishing(true);
    setPublishStatus(null);

    try {
      let finalUrl = videoUrl;

      // If a local file was selected, upload it first
      if (videoFile) {
        setUploadProgress("Uploading video to server...");
        const formData = new FormData();
        formData.append("file", videoFile);

        const uploadRes = await fetch(`${backendUrl}/tiktok/videos/upload`, {
          method: "POST",
          body: formData,
        });
        const uploadData = await uploadRes.json();
        if (!uploadRes.ok) throw new Error(uploadData.detail || "Failed to upload video");
        finalUrl = uploadData.video_url;
        setUploadProgress("Video uploaded! Sending to TikTok...");
      }

      const res = await fetch(
        `${backendUrl}/tiktok/videos/publish?account_id=${accountId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: caption,
            video_url: finalUrl,
            privacy_level: privacyLevel,
          }),
        }
      );
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 401) {
          setPublishStatus({
            type: "auth",
            message: data.detail || "TikTok session expired. Please re-authenticate.",
          });
        } else {
          throw new Error(data.detail || "Failed to publish video");
        }
        return;
      }

      setPublishStatus({
        type: "success",
        message: `Video submitted! Publish ID: ${data.publish_id}. TikTok is processing your video.`,
      });
      setVideoUrl("");
      setVideoFile(null);
      setCaption("");
      setUploadProgress("");
    } catch (err) {
      const isAuth = err.message?.toLowerCase().includes("re-authenticate") ||
                     err.message?.toLowerCase().includes("expired") ||
                     err.message?.toLowerCase().includes("token");
      setPublishStatus({
        type: isAuth ? "auth" : "error",
        message: err.message,
      });
      setUploadProgress("");
    } finally {
      setIsPublishing(false);
    }
  };

  // ─── Drag & drop for video URL ────────────────────────────────────

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
    else if (e.type === "dragleave") setDragActive(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    // If a file was dropped, use it
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.type.startsWith("video/")) {
        setVideoFile(file);
        setVideoUrl("");
        return;
      }
    }
    // If a URL was dropped (text), use it
    const droppedText = e.dataTransfer.getData("text");
    if (droppedText && droppedText.startsWith("http")) {
      setVideoUrl(droppedText);
      setVideoFile(null);
    }
  };

  // ─── Formatting helpers ───────────────────────────────────────────

  const fmtNum = (n) => {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
    if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
    return String(n);
  };

  const fmtDate = (timestamp) => {
    if (!timestamp) return "";
    return new Date(timestamp * 1000).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  // ─── Tab definitions ──────────────────────────────────────────────

  const tabs = [
    { id: "analytics", label: "Analytics", icon: analyticsIcon },
    { id: "videos", label: "Videos", icon: videosIcon },
    { id: "publish", label: "Publish", icon: publishIcon },
  ];

  // ─── Loading & Error states ───────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-4 border-gray-200 border-t-pink-500 rounded-full animate-spin" />
          <p className="text-sm text-gray-500">Loading TikTok data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
        <p className="text-red-700 font-medium mb-2">
          {needsReauth ? "TikTok Session Expired" : "Failed to load TikTok data"}
        </p>
        <p className="text-red-500 text-sm mb-4">{error}</p>
        <div className="flex items-center justify-center gap-3">
          {needsReauth ? (
            <a
              href={`${backendUrl}/tiktok/auth/login`}
              className="px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-black transition"
            >
              Re-connect TikTok
            </a>
          ) : (
            <button
              onClick={fetchAnalytics}
              className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 transition"
            >
              Retry
            </button>
          )}
        </div>
      </div>
    );
  }

  const profile = analytics?.profile || {};
  const metrics = analytics?.metrics || {};
  const videos = analytics?.recent_videos || [];

  return (
    <div className="space-y-6">
      {/* ─── Profile Header ─────────────────────────────────────── */}
      <div className="bg-gradient-to-r from-gray-900 via-gray-800 to-pink-900 rounded-2xl p-6 text-white">
        <div className="flex items-start gap-5">
          {profile.avatar_url ? (
            <img
              src={profile.avatar_url}
              alt={profile.display_name}
              className="w-20 h-20 rounded-full border-3 border-white/30 shadow-lg flex-shrink-0"
            />
          ) : (
            <div className="w-20 h-20 rounded-full bg-white/10 flex items-center justify-center flex-shrink-0">
              <svg className="w-10 h-10 text-white/50" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
              </svg>
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-xl font-bold">{profile.display_name || "TikTok User"}</h2>
              {profile.is_verified && (
                <span className="bg-blue-500 rounded-full p-0.5">
                  <svg className="w-3.5 h-3.5 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                  </svg>
                </span>
              )}
            </div>
            {profile.bio_description && (
              <p className="text-white/70 text-sm mt-1 max-w-lg">{profile.bio_description}</p>
            )}
            {/* Profile link */}
            {(profile.profile_deep_link || profile.profile_web_link) && (
              <a
                href={profile.profile_web_link || profile.profile_deep_link}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-2 text-xs text-pink-300 hover:text-pink-200 transition"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                View on TikTok
              </a>
            )}
            {/* Inline follower stats */}
            <div className="flex items-center gap-5 mt-3">
              <div className="text-center">
                <p className="text-lg font-bold">{fmtNum(profile.follower_count || metrics.followers)}</p>
                <p className="text-[11px] text-white/50">Followers</p>
              </div>
              <div className="text-center">
                <p className="text-lg font-bold">{fmtNum(profile.following_count || metrics.following)}</p>
                <p className="text-[11px] text-white/50">Following</p>
              </div>
              <div className="text-center">
                <p className="text-lg font-bold">{fmtNum(profile.likes_count || metrics.total_likes)}</p>
                <p className="text-[11px] text-white/50">Likes</p>
              </div>
              <div className="text-center">
                <p className="text-lg font-bold">{fmtNum(profile.video_count || metrics.total_videos)}</p>
                <p className="text-[11px] text-white/50">Videos</p>
              </div>
            </div>
          </div>
          <button
            onClick={fetchAnalytics}
            className="p-2 hover:bg-white/10 rounded-lg transition flex-shrink-0"
            title="Refresh data"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
          </button>
        </div>
      </div>

      {/* ─── Tab Navigation ─────────────────────────────────────── */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-sm font-medium transition-all ${
              activeTab === tab.id
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <span dangerouslySetInnerHTML={{ __html: tab.icon }} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* ─── Analytics Tab ──────────────────────────────────────── */}
      {activeTab === "analytics" && (
        <div className="space-y-6">
          {/* Metric cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              label="Followers"
              value={fmtNum(metrics.followers)}
              icon={followersIcon}
              color="pink"
            />
            <MetricCard
              label="Total Views"
              value={fmtNum(metrics.total_views)}
              icon={viewsIcon}
              color="blue"
            />
            <MetricCard
              label="Total Likes"
              value={fmtNum(metrics.total_likes)}
              icon={likesIcon}
              color="red"
            />
            <MetricCard
              label="Engagement"
              value={`${metrics.engagement_rate}%`}
              icon={engagementIcon}
              color="green"
            />
          </div>

          {/* Secondary metrics */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-gray-900">{fmtNum(metrics.total_videos)}</p>
              <p className="text-xs text-gray-500 mt-1">Videos</p>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-gray-900">{fmtNum(metrics.total_comments)}</p>
              <p className="text-xs text-gray-500 mt-1">Comments</p>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-gray-900">{fmtNum(metrics.total_shares)}</p>
              <p className="text-xs text-gray-500 mt-1">Shares</p>
            </div>
          </div>
        </div>
      )}

      {/* ─── Videos Tab ─────────────────────────────────────────── */}
      {activeTab === "videos" && (
        <VideoGrid videos={videos} fmtNum={fmtNum} fmtDate={fmtDate} />
      )}

      {/* ─── Publish Tab ────────────────────────────────────────── */}
      {activeTab === "publish" && (
        <div className="max-w-2xl mx-auto">
          <form onSubmit={handlePublish} className="space-y-5">
            {/* Drag & drop / URL input area */}
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${
                dragActive
                  ? "border-pink-400 bg-pink-50"
                  : videoFile
                    ? "border-green-400 bg-green-50"
                    : "border-gray-300 bg-gray-50 hover:border-gray-400"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.[0]) {
                    setVideoFile(e.target.files[0]);
                    setVideoUrl("");
                  }
                }}
                disabled={isPublishing}
              />
              {videoFile ? (
                <>
                  <svg className="w-10 h-10 mx-auto mb-3 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"/>
                  </svg>
                  <p className="text-sm text-green-700 font-medium mb-1">{videoFile.name}</p>
                  <p className="text-xs text-green-500">
                    {(videoFile.size / (1024 * 1024)).toFixed(1)} MB — Click to change
                  </p>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setVideoFile(null); }}
                    className="mt-2 text-xs text-red-500 hover:text-red-700 underline"
                  >
                    Remove
                  </button>
                </>
              ) : (
                <>
                  <svg className="w-10 h-10 mx-auto mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
                  </svg>
                  <p className="text-sm text-gray-600 font-medium mb-1">
                    Click to select a video or drag & drop
                  </p>
                  <p className="text-xs text-gray-400">
                    MP4, MOV, AVI, WebM — or paste a URL below
                  </p>
                </>
              )}
            </div>

            {/* Divider */}
            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-gray-200" />
              <span className="text-xs text-gray-400">or use a URL</span>
              <div className="flex-1 h-px bg-gray-200" />
            </div>

            {/* Video URL input */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Video URL
              </label>
              <input
                type="url"
                value={videoUrl}
                onChange={(e) => { setVideoUrl(e.target.value); if (e.target.value) setVideoFile(null); }}
                placeholder="https://your-bucket.s3.amazonaws.com/video.mp4"
                className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-pink-500 focus:border-pink-500 transition"
                disabled={isPublishing || !!videoFile}
              />
            </div>

            {/* Caption / hashtags */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Caption & Hashtags
              </label>
              <textarea
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                placeholder="Check out this amazing video! #trending #viral #fyp"
                maxLength={150}
                rows={3}
                className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-pink-500 focus:border-pink-500 transition resize-none"
                required
                disabled={isPublishing}
              />
              <p className="text-xs text-gray-400 mt-1 text-right">
                {caption.length}/150
              </p>
            </div>

            {/* Privacy selector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Privacy Level
              </label>
              <select
                value={privacyLevel}
                onChange={(e) => setPrivacyLevel(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-pink-500 focus:border-pink-500 transition"
                disabled={isPublishing}
              >
                <option value="PUBLIC_TO_EVERYONE">Public</option>
                <option value="MUTUAL_FOLLOW_FRIENDS">Friends</option>
                <option value="FOLLOWER_OF_CREATOR">Followers Only</option>
                <option value="SELF_ONLY">Only Me</option>
              </select>
            </div>

            {/* Upload progress */}
            {uploadProgress && (
              <div className="bg-blue-50 text-blue-700 border border-blue-200 rounded-lg p-4 text-sm flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-blue-300 border-t-blue-600 rounded-full animate-spin" />
                {uploadProgress}
              </div>
            )}

            {/* Status messages */}
            {publishStatus && (
              <div
                className={`rounded-lg p-4 text-sm ${
                  publishStatus.type === "success"
                    ? "bg-green-50 text-green-700 border border-green-200"
                    : publishStatus.type === "auth"
                      ? "bg-amber-50 text-amber-800 border border-amber-200"
                      : "bg-red-50 text-red-700 border border-red-200"
                }`}
              >
                <p>{publishStatus.message}</p>
                {publishStatus.type === "auth" && (
                  <a
                    href={`${backendUrl}/tiktok/auth/login`}
                    className="mt-3 inline-flex items-center gap-2 px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-black transition"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    Re-connect TikTok
                  </a>
                )}
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={isPublishing || (!videoUrl.trim() && !videoFile)}
              className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-pink-500 to-rose-500 text-white py-3 px-6 rounded-xl text-sm font-semibold hover:from-pink-600 hover:to-rose-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-pink-500/25"
            >
              {isPublishing ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Publishing...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
                  </svg>
                  Post to TikTok
                </>
              )}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Video Grid with Playable Embeds
// ═══════════════════════════════════════════════════════════════════════════════

function VideoGrid({ videos, fmtNum, fmtDate }) {
  const [playingId, setPlayingId] = useState(null);

  if (videos.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        <svg className="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/>
        </svg>
        <p className="text-sm">No videos found</p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {videos.map((video) => (
          <div
            key={video.id}
            className="bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-lg transition-shadow group"
          >
            {/* Thumbnail with play button overlay */}
            <div className="relative aspect-[9/16] max-h-72 bg-gray-900 overflow-hidden">
              {video.cover_image_url ? (
                <img
                  src={video.cover_image_url}
                  alt={video.title || video.video_description}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 opacity-90"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-gray-100 text-gray-300">
                  <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                  </svg>
                </div>
              )}

              {/* Play button overlay */}
              {(video.share_url || video.embed_link) && (
                <button
                  onClick={() => setPlayingId(video.id)}
                  className="absolute inset-0 flex items-center justify-center bg-black/20 hover:bg-black/40 transition-colors group/play"
                >
                  <div className="w-14 h-14 rounded-full bg-white/90 flex items-center justify-center shadow-xl group-hover/play:scale-110 transition-transform">
                    <svg className="w-7 h-7 text-gray-900 ml-1" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M8 5v14l11-7z"/>
                    </svg>
                  </div>
                </button>
              )}

              {/* Duration badge */}
              {video.duration > 0 && (
                <span className="absolute bottom-2 right-2 bg-black/80 text-white text-xs px-2 py-0.5 rounded font-mono">
                  {Math.floor(video.duration / 60)}:{String(video.duration % 60).padStart(2, "0")}
                </span>
              )}
            </div>

            {/* Video info */}
            <div className="p-4">
              <p className="text-sm font-semibold text-gray-900 line-clamp-2 min-h-[2.5rem]">
                {video.title || video.video_description || "(untitled)"}
              </p>
              <p className="text-xs text-gray-400 mt-1">{fmtDate(video.create_time)}</p>

              {/* Stats row */}
              <div className="grid grid-cols-4 gap-1 mt-3 pt-3 border-t border-gray-100">
                <div className="text-center">
                  <p className="text-sm font-bold text-gray-900">{fmtNum(video.view_count)}</p>
                  <p className="text-[10px] text-gray-400">Views</p>
                </div>
                <div className="text-center">
                  <p className="text-sm font-bold text-gray-900">{fmtNum(video.like_count)}</p>
                  <p className="text-[10px] text-gray-400">Likes</p>
                </div>
                <div className="text-center">
                  <p className="text-sm font-bold text-gray-900">{fmtNum(video.comment_count)}</p>
                  <p className="text-[10px] text-gray-400">Comments</p>
                </div>
                <div className="text-center">
                  <p className="text-sm font-bold text-gray-900">{fmtNum(video.share_count)}</p>
                  <p className="text-[10px] text-gray-400">Shares</p>
                </div>
              </div>

              {/* Watch on TikTok link */}
              {video.share_url && (
                <a
                  href={video.share_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 flex items-center justify-center gap-1.5 text-xs text-pink-600 hover:text-pink-700 font-medium transition"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                  Watch on TikTok
                </a>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* ─── Video Player Modal ─────────────────────────────────── */}
      {playingId && (() => {
        const video = videos.find(v => v.id === playingId);
        if (!video) return null;
        // Build TikTok embed URL from share_url or embed_link
        const embedSrc = video.embed_link
          || (video.share_url ? `https://www.tiktok.com/embed/v2/${video.id}` : "");
        return (
          <div
            className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
            onClick={() => setPlayingId(null)}
          >
            <div
              className="relative bg-black rounded-2xl overflow-hidden shadow-2xl"
              style={{ width: 380, maxHeight: "90vh" }}
              onClick={e => e.stopPropagation()}
            >
              {/* Close button */}
              <button
                onClick={() => setPlayingId(null)}
                className="absolute top-3 right-3 z-10 bg-black/50 hover:bg-black/70 text-white rounded-full p-1.5 transition"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>

              {/* Embedded TikTok player */}
              {embedSrc ? (
                <iframe
                  src={embedSrc}
                  className="w-full border-0"
                  style={{ height: 700, maxHeight: "85vh" }}
                  allowFullScreen
                  allow="encrypted-media"
                  title={video.title || "TikTok Video"}
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-96 text-white/70">
                  <p className="text-sm mb-3">Embed not available for this video</p>
                  {video.share_url && (
                    <a
                      href={video.share_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-4 py-2 bg-pink-600 text-white rounded-lg text-sm hover:bg-pink-700 transition"
                    >
                      Open on TikTok
                    </a>
                  )}
                </div>
              )}

              {/* Video info bar */}
              <div className="bg-gray-900 p-4 text-white">
                <p className="text-sm font-medium truncate">{video.title || video.video_description || "(untitled)"}</p>
                <div className="flex items-center gap-4 mt-2 text-xs text-white/60">
                  <span>{fmtNum(video.view_count)} views</span>
                  <span>{fmtNum(video.like_count)} likes</span>
                  <span>{fmtNum(video.comment_count)} comments</span>
                </div>
              </div>
            </div>
          </div>
        );
      })()}
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Metric Card Component
// ═══════════════════════════════════════════════════════════════════════════════

const colorMap = {
  pink: { bg: "bg-pink-50", text: "text-pink-600", border: "border-pink-100" },
  blue: { bg: "bg-blue-50", text: "text-blue-600", border: "border-blue-100" },
  red: { bg: "bg-red-50", text: "text-red-600", border: "border-red-100" },
  green: { bg: "bg-green-50", text: "text-green-600", border: "border-green-100" },
};

function MetricCard({ label, value, icon, color = "pink" }) {
  const c = colorMap[color] || colorMap.pink;
  return (
    <div className={`bg-white border ${c.border} rounded-xl p-5 transition hover:shadow-md`}>
      <div className="flex items-center justify-between mb-3">
        <div
          className={`w-10 h-10 ${c.bg} rounded-lg flex items-center justify-center`}
          dangerouslySetInnerHTML={{ __html: icon }}
        />
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-500 mt-1">{label}</p>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SVG Icon strings (inline for simplicity)
// ═══════════════════════════════════════════════════════════════════════════════

const analyticsIcon = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>`;

const videosIcon = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>`;

const publishIcon = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg>`;

const followersIcon = `<svg class="w-5 h-5 text-pink-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg>`;

const viewsIcon = `<svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>`;

const likesIcon = `<svg class="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/></svg>`;

const engagementIcon = `<svg class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>`;
