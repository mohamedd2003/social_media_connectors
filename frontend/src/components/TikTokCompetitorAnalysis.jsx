import { useState } from "react";

/**
 * TikTokCompetitorAnalysis – Search any public TikTok username and view
 * their profile stats + latest videos via the Apify scraper backend.
 */
export default function TikTokCompetitorAnalysis({ backendUrl = "" }) {
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const handleAnalyze = async () => {
    const clean = username.trim().replace(/^@/, "");
    if (!clean) return;

    setLoading(true);
    setError(null);
    setData(null);

    try {
      const res = await fetch(
        `${backendUrl}/api/v1/tiktok/competitor/${encodeURIComponent(clean)}`
      );
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.detail || "Failed to fetch competitor data.");
      }

      setData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleAnalyze();
  };

  const fmt = (n) => {
    if (n == null) return "—";
    if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + "B";
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
    if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
    return n.toLocaleString();
  };

  const formatDuration = (seconds) => {
    const s = Number(seconds || 0);
    if (!s) return "0:00";
    const mins = Math.floor(s / 60);
    const rem = s % 60;
    return `${mins}:${String(rem).padStart(2, "0")}`;
  };

  const shortText = (value, fallback = "-") => {
    if (value == null || String(value).trim() === "") return fallback;
    return value;
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="mb-6">
        <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <svg className="w-6 h-6" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1v-3.5a6.37 6.37 0 00-.79-.05A6.34 6.34 0 003.15 15.2a6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.34-6.34V8.72a8.2 8.2 0 004.76 1.52V6.8a4.84 4.84 0 01-1-.11z" />
          </svg>
          TikTok Competitor Analysis
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          Enter a TikTok username to scrape their public profile and recent
          videos.
        </p>
      </div>

      {/* ── Search Bar ──────────────────────────────────────────── */}
      <div className="flex gap-3 mb-6">
        <div className="relative flex-1">
          <span className="absolute inset-y-0 left-3 flex items-center text-gray-400 pointer-events-none select-none">
            @
          </span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="khaby.lame"
            className="w-full pl-8 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gray-900 focus:border-gray-900 outline-none transition"
            disabled={loading}
          />
        </div>
        <button
          onClick={handleAnalyze}
          disabled={loading || !username.trim()}
          className="px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-black disabled:opacity-50 transition flex items-center gap-2"
        >
          {loading ? (
            <>
              <svg
                className="animate-spin h-4 w-4"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              Analyzing…
            </>
          ) : (
            "Analyze"
          )}
        </button>
      </div>

      {/* ── Loading Skeleton ────────────────────────────────────── */}
      {loading && (
        <div className="space-y-6 animate-pulse">
          {/* Profile skeleton */}
          <div className="bg-white border border-gray-200 rounded-xl p-6 flex items-center gap-6">
            <div className="w-20 h-20 bg-gray-200 rounded-full shrink-0" />
            <div className="flex-1 space-y-3">
              <div className="h-5 bg-gray-200 rounded w-40" />
              <div className="h-4 bg-gray-200 rounded w-28" />
            </div>
            <div className="flex gap-8">
              {[1, 2, 3].map((i) => (
                <div key={i} className="text-center space-y-2">
                  <div className="h-6 bg-gray-200 rounded w-16 mx-auto" />
                  <div className="h-3 bg-gray-200 rounded w-12 mx-auto" />
                </div>
              ))}
            </div>
          </div>
          {/* Video skeletons */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="bg-white border border-gray-200 rounded-xl p-4 space-y-3"
              >
                <div className="h-4 bg-gray-200 rounded w-full" />
                <div className="h-4 bg-gray-200 rounded w-3/4" />
                <div className="flex gap-4 mt-4">
                  <div className="h-4 bg-gray-200 rounded w-16" />
                  <div className="h-4 bg-gray-200 rounded w-16" />
                  <div className="h-4 bg-gray-200 rounded w-16" />
                </div>
              </div>
            ))}
          </div>
          <p className="text-center text-sm text-gray-500">
            Scraping TikTok data, please wait… This may take 5–15 seconds.
          </p>
        </div>
      )}

      {/* ── Error Banner ────────────────────────────────────────── */}
      {error && !loading && (
        <div className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg text-sm mb-6">
          <svg
            className="w-5 h-5 shrink-0 mt-0.5 text-red-500"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clipRule="evenodd"
            />
          </svg>
          <div>
            <p className="font-medium">Analysis failed</p>
            <p className="mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* ── Results ─────────────────────────────────────────────── */}
      {data && !loading && (
        <div className="space-y-6">
          {/* Profile Card */}
          <div className="bg-white border border-gray-200 rounded-xl p-6 flex flex-col sm:flex-row items-center gap-6">
            {data.avatar && (
              <img
                src={data.avatar}
                alt={data.displayName}
                className="w-20 h-20 rounded-full object-cover border-2 border-gray-200 shrink-0"
              />
            )}
            <div className="flex-1 text-center sm:text-left">
              <h3 className="text-lg font-bold text-gray-900 flex items-center justify-center sm:justify-start gap-2">
                <span>{data.displayName || data.username}</span>
                {data.isVerified && (
                  <span
                    className="inline-flex items-center text-[11px] font-semibold text-blue-700 bg-blue-100 px-2 py-0.5 rounded-full"
                    title="Verified account"
                  >
                    <svg className="w-3 h-3 mr-1" viewBox="0 0 20 20" fill="currentColor">
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.78-9.72a.75.75 0 10-1.06-1.06L9 10.94 7.28 9.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.06 0l4.25-4.25z"
                        clipRule="evenodd"
                      />
                    </svg>
                    Verified
                  </span>
                )}
              </h3>
              <p className="text-sm text-gray-500">@{data.username}</p>
              {data.bio && (
                <p className="text-sm text-gray-700 mt-2 max-w-2xl whitespace-pre-wrap">
                  {data.bio}
                </p>
              )}
              <div className="flex flex-wrap justify-center sm:justify-start gap-2 mt-3 text-xs">
                <span className="px-2 py-1 bg-gray-100 text-gray-600 rounded">
                  Region: {shortText(data.region)}
                </span>
                <span className="px-2 py-1 bg-gray-100 text-gray-600 rounded">
                  Language: {shortText(data.language)}
                </span>
              </div>
            </div>
            <div className="flex gap-8 sm:gap-10">
              <div className="text-center">
                <p className="text-xl font-bold text-gray-900">
                  {fmt(data.followers)}
                </p>
                <p className="text-xs text-gray-500 uppercase tracking-wide">
                  Followers
                </p>
              </div>
              <div className="text-center">
                <p className="text-xl font-bold text-gray-900">
                  {fmt(data.following)}
                </p>
                <p className="text-xs text-gray-500 uppercase tracking-wide">
                  Following
                </p>
              </div>
              <div className="text-center">
                <p className="text-xl font-bold text-gray-900">
                  {fmt(data.totalLikes)}
                </p>
                <p className="text-xs text-gray-500 uppercase tracking-wide">
                  Total Likes
                </p>
              </div>
            </div>
          </div>

          {/* Latest Videos */}
          {data.latestVideos && data.latestVideos.length > 0 && (
            <div>
              <h3 className="text-base font-semibold text-gray-900 mb-3">
                Videos ({data.latestVideos.length})
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {data.latestVideos.map((vid, i) => (
                  <div
                    key={vid.videoUrl || `video-${i}`}
                    className="bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-md transition"
                  >
                    <div
                      className="h-52 bg-gray-100 bg-cover bg-center relative"
                      style={
                        vid.coverUrl
                          ? { backgroundImage: `url(${vid.coverUrl})` }
                          : undefined
                      }
                    >
                      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/25 to-black/5" />
                      <div className="absolute bottom-0 left-0 right-0 p-3 text-white">
                        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs font-medium">
                          <span>Views: {fmt(vid.viewCount)}</span>
                          <span>Likes: {fmt(vid.likeCount)}</span>
                          <span>Comments: {fmt(vid.commentCount)}</span>
                          <span>Shares: {fmt(vid.shareCount)}</span>
                        </div>
                      </div>
                    </div>

                    <div className="p-4">
                      <p className="text-sm text-gray-800 min-h-[3.6em] line-clamp-3">
                        {vid.description || "(no caption)"}
                      </p>

                      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-600">
                        <span className="px-2 py-1 bg-gray-100 rounded">
                          Duration: {formatDuration(vid.duration)}
                        </span>
                        <span className="px-2 py-1 bg-gray-100 rounded">
                          Format: {shortText(vid.format)}
                        </span>
                        <span className="px-2 py-1 bg-gray-100 rounded col-span-2">
                          Downloads: {fmt(vid.downloadCount)}
                        </span>
                        <span className="px-2 py-1 bg-gray-100 rounded col-span-2 truncate" title={vid.musicTitle || ""}>
                          Music: {shortText(vid.musicTitle)}
                        </span>
                        <span className="px-2 py-1 bg-gray-100 rounded col-span-2 truncate" title={vid.musicAuthor || ""}>
                          Artist: {shortText(vid.musicAuthor)}
                        </span>
                      </div>

                      <div className="mt-3 flex items-center justify-between text-xs">
                        {vid.createdAt && (
                          <span className="text-gray-400">
                            {new Date(vid.createdAt).toLocaleDateString()}
                          </span>
                        )}
                        {vid.videoUrl && (
                          <a
                            href={vid.videoUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-gray-900 font-medium hover:underline"
                          >
                            Watch &rarr;
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
