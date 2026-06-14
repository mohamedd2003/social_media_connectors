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

  // Publish form state
  const [videoUrl, setVideoUrl] = useState("");
  const [caption, setCaption] = useState("");
  const [privacyLevel, setPrivacyLevel] = useState("PUBLIC_TO_EVERYONE");
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishStatus, setPublishStatus] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  // ─── Fetch analytics data ──────────────────────────────────────────

  const fetchAnalytics = useCallback(async () => {
    if (!accountId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${backendUrl}/tiktok/profile/analytics?account_id=${accountId}`
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load TikTok analytics");
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
    if (!videoUrl.trim() || !caption.trim()) return;

    setIsPublishing(true);
    setPublishStatus(null);

    try {
      const res = await fetch(
        `${backendUrl}/tiktok/videos/publish?account_id=${accountId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: caption,
            video_url: videoUrl,
            privacy_level: privacyLevel,
          }),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to publish video");

      setPublishStatus({
        type: "success",
        message: `Video submitted! Publish ID: ${data.publish_id}. TikTok is processing your video.`,
      });
      setVideoUrl("");
      setCaption("");
    } catch (err) {
      setPublishStatus({ type: "error", message: err.message });
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
    // If a URL was dropped (text), use it
    const droppedText = e.dataTransfer.getData("text");
    if (droppedText && droppedText.startsWith("http")) {
      setVideoUrl(droppedText);
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
        <p className="text-red-700 font-medium mb-2">Failed to load TikTok data</p>
        <p className="text-red-500 text-sm mb-4">{error}</p>
        <button
          onClick={fetchAnalytics}
          className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 transition"
        >
          Retry
        </button>
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
        <div className="flex items-center gap-5">
          {profile.avatar_url ? (
            <img
              src={profile.avatar_url}
              alt={profile.display_name}
              className="w-16 h-16 rounded-full border-2 border-white/30 shadow-lg"
            />
          ) : (
            <div className="w-16 h-16 rounded-full bg-white/10 flex items-center justify-center">
              <svg className="w-8 h-8 text-white/50" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
              </svg>
            </div>
          )}
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold">{profile.display_name || "TikTok User"}</h2>
              {profile.is_verified && (
                <svg className="w-5 h-5 text-blue-400" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                </svg>
              )}
            </div>
            {profile.bio_description && (
              <p className="text-white/70 text-sm mt-1 max-w-lg">{profile.bio_description}</p>
            )}
          </div>
          <button
            onClick={fetchAnalytics}
            className="p-2 hover:bg-white/10 rounded-lg transition"
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
        <div>
          {videos.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <svg className="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/>
              </svg>
              <p className="text-sm">No videos found</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {videos.map((video) => (
                <div
                  key={video.id}
                  className="bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-md transition-shadow group"
                >
                  {/* Thumbnail */}
                  <div className="relative aspect-[9/16] max-h-64 bg-gray-100 overflow-hidden">
                    {video.cover_image_url ? (
                      <img
                        src={video.cover_image_url}
                        alt={video.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-gray-300">
                        <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                        </svg>
                      </div>
                    )}
                    {/* Duration badge */}
                    {video.duration > 0 && (
                      <span className="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-2 py-0.5 rounded">
                        {Math.floor(video.duration / 60)}:{String(video.duration % 60).padStart(2, "0")}
                      </span>
                    )}
                  </div>

                  {/* Video info */}
                  <div className="p-3">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {video.title || "(untitled)"}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">{fmtDate(video.create_time)}</p>

                    {/* Stats row */}
                    <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                      <span className="flex items-center gap-1" title="Views">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                        {fmtNum(video.view_count)}
                      </span>
                      <span className="flex items-center gap-1" title="Likes">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/></svg>
                        {fmtNum(video.like_count)}
                      </span>
                      <span className="flex items-center gap-1" title="Comments">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
                        {fmtNum(video.comment_count)}
                      </span>
                      <span className="flex items-center gap-1" title="Shares">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"/></svg>
                        {fmtNum(video.share_count)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
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
              className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
                dragActive
                  ? "border-pink-400 bg-pink-50"
                  : "border-gray-300 bg-gray-50 hover:border-gray-400"
              }`}
            >
              <svg className="w-10 h-10 mx-auto mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
              </svg>
              <p className="text-sm text-gray-600 font-medium mb-1">
                Drop a video URL here, or paste it below
              </p>
              <p className="text-xs text-gray-400">
                TikTok requires a publicly accessible URL (e.g., S3, Cloud Storage)
              </p>
            </div>

            {/* Video URL input */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Video URL
              </label>
              <input
                type="url"
                value={videoUrl}
                onChange={(e) => setVideoUrl(e.target.value)}
                placeholder="https://your-bucket.s3.amazonaws.com/video.mp4"
                className="w-full border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-pink-500 focus:border-pink-500 transition"
                required
                disabled={isPublishing}
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

            {/* Status messages */}
            {publishStatus && (
              <div
                className={`rounded-lg p-4 text-sm ${
                  publishStatus.type === "success"
                    ? "bg-green-50 text-green-700 border border-green-200"
                    : "bg-red-50 text-red-700 border border-red-200"
                }`}
              >
                {publishStatus.message}
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={isPublishing || !videoUrl.trim() || !caption.trim()}
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
