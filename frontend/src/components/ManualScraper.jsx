import { useState } from "react";

const PLATFORMS = [
  { id: "tiktok", label: "TikTok", icon: "🎵", color: "from-gray-900 to-gray-700" },
  { id: "instagram", label: "Instagram", icon: "📸", color: "from-pink-500 via-rose-500 to-orange-500" },
  { id: "facebook", label: "Facebook", icon: "📘", color: "from-blue-600 to-blue-500" },
];

function fmt(n) {
  if (n == null) return "-";
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + "B";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return Number(n).toLocaleString();
}

function proxyUrl(url) {
  if (!url) return "";
  const cdnHosts = ["instagram", "cdninstagram", "fbcdn", "scontent", "tiktokcdn", "p16-sign", "p77-sign", "p19-sign"];
  try {
    const host = new URL(url).hostname;
    if (cdnHosts.some((h) => host.includes(h))) {
      return `/api/proxy-image?url=${encodeURIComponent(url)}`;
    }
  } catch (e) {}
  return url;
}

function shortText(value, fallback = "-") {
  if (value == null || String(value).trim() === "") return fallback;
  return value;
}

function formatDuration(seconds) {
  if (seconds == null || seconds === "") return "-";
  const s = Number(seconds);
  if (!Number.isFinite(s) || s <= 0) return "-";
  const mins = Math.floor(s / 60);
  const rem = s % 60;
  return `${mins}:${String(rem).padStart(2, "0")}`;
}

/* ══════════════════════════════════════════════════════════════════
   TikTok Results – Identical to TikTokCompetitorAnalysis.jsx
   ══════════════════════════════════════════════════════════════════ */
function TikTokResults({ data }) {
  return (
    <div className="space-y-6">
      {/* Profile Card */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 flex flex-col sm:flex-row items-center gap-6">
        {data.avatar ? (
          <img
            src={proxyUrl(data.avatar)}
            alt={data.display_name}
            className="w-20 h-20 rounded-full object-cover border-2 border-gray-200 shrink-0"
          />
        ) : (
          <div className="w-20 h-20 rounded-full bg-gray-200 shrink-0" />
        )}
        <div className="flex-1 text-center sm:text-left">
          <h3 className="text-lg font-bold text-gray-900 flex items-center justify-center sm:justify-start gap-2">
            <span>{data.display_name || data.username}</span>
            {data.is_verified && (
              <span className="inline-flex items-center text-[11px] font-semibold text-blue-700 bg-blue-100 px-2 py-0.5 rounded-full" title="Verified account">
                <svg className="w-3 h-3 mr-1" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.78-9.72a.75.75 0 10-1.06-1.06L9 10.94 7.28 9.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.06 0l4.25-4.25z" clipRule="evenodd" />
                </svg>
                Verified
              </span>
            )}
          </h3>
          <p className="text-sm text-gray-500">@{data.username}</p>
          {data.bio && (
            <p className="text-sm text-gray-700 mt-2 max-w-2xl whitespace-pre-wrap">{data.bio}</p>
          )}
          <div className="flex flex-wrap justify-center sm:justify-start gap-2 mt-3 text-xs">
            <span className="px-2 py-1 bg-gray-100 text-gray-600 rounded">Region: {shortText(data.region)}</span>
            <span className="px-2 py-1 bg-gray-100 text-gray-600 rounded">Language: {shortText(data.language)}</span>
          </div>
        </div>
        <div className="flex gap-8 sm:gap-10">
          <div className="text-center">
            <p className="text-xl font-bold text-gray-900">{fmt(data.followers)}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Followers</p>
          </div>
          <div className="text-center">
            <p className="text-xl font-bold text-gray-900">{fmt(data.following)}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Following</p>
          </div>
          <div className="text-center">
            <p className="text-xl font-bold text-gray-900">{fmt(data.likes)}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Total Likes</p>
          </div>
        </div>
      </div>

      {/* Latest Videos */}
      {data.recent_posts && data.recent_posts.length > 0 && (
        <div>
          <h3 className="text-base font-semibold text-gray-900 mb-3">
            Videos ({data.posts_count || data.recent_posts.length})
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.recent_posts.map((vid, i) => (
              <div
                key={vid.url || `video-${i}`}
                className="bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-md transition"
              >
                <div
                  className="h-52 bg-gray-100 bg-cover bg-center relative"
                  style={
                    vid.thumbnail
                      ? { backgroundImage: `url(${proxyUrl(vid.thumbnail)})` }
                      : undefined
                  }
                >
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/25 to-black/5" />
                  <div className="absolute bottom-0 left-0 right-0 p-3 text-white">
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs font-medium">
                      <span>Views: {fmt(vid.views)}</span>
                      <span>Likes: {fmt(vid.likes)}</span>
                      <span>Comments: {fmt(vid.comments)}</span>
                      <span>Shares: {fmt(vid.shares)}</span>
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
                      Downloads: {fmt(vid.downloads)}
                    </span>
                    <span className="px-2 py-1 bg-gray-100 rounded col-span-2 truncate" title={vid.music_title || ""}>
                      Music: {shortText(vid.music_title)}
                    </span>
                    <span className="px-2 py-1 bg-gray-100 rounded col-span-2 truncate" title={vid.music_author || ""}>
                      Artist: {shortText(vid.music_author)}
                    </span>
                  </div>

                  <div className="mt-3 flex items-center justify-between text-xs">
                    {vid.created_at && (
                      <span className="text-gray-400">
                        {new Date(vid.created_at).toLocaleDateString()}
                      </span>
                    )}
                    {vid.url && (
                      <a
                        href={vid.url}
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

      {(!data.recent_posts || data.recent_posts.length === 0) && (
        <p className="text-sm text-gray-500">No videos found for this account.</p>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   Instagram Results – Identical to InstagramCompetitorAnalysis.jsx
   ══════════════════════════════════════════════════════════════════ */
function InstagramResults({ data }) {
  const [failedImages, setFailedImages] = useState({});
  const postKey = (post, index) => post.id || post.url || `post-${index}`;

  return (
    <div className="space-y-6">
      {/* Profile Card */}
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="flex flex-col sm:flex-row sm:items-center gap-5">
          {data.avatar ? (
            <img
              src={proxyUrl(data.avatar)}
              alt={data.display_name || data.username}
              className="w-20 h-20 rounded-full object-cover border border-gray-200"
            />
          ) : (
            <div className="w-20 h-20 rounded-full bg-gray-200" />
          )}

          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-lg font-bold text-gray-900">
                {data.display_name || data.username}
              </h3>
              {data.is_verified && (
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-blue-700 bg-blue-100 px-2 py-1 rounded-full">
                  <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.707a1 1 0 00-1.414-1.414L9 10.172 7.707 8.879a1 1 0 10-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Verified
                </span>
              )}
            </div>
            <p className="text-sm text-gray-500">@{data.username}</p>
            {data.bio && (
              <p className="text-sm text-gray-700 mt-2 whitespace-pre-wrap">{data.bio}</p>
            )}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 mt-6">
          <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
            <p className="text-xl font-bold text-gray-900">{fmt(data.followers)}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Followers</p>
          </div>
          <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
            <p className="text-xl font-bold text-gray-900">{fmt(data.following)}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Following</p>
          </div>
          <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
            <p className="text-xl font-bold text-gray-900">{fmt(data.posts_count)}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Total Posts</p>
          </div>
        </div>
      </div>

      {/* Latest Posts */}
      <div>
        <h3 className="text-base font-semibold text-gray-900 mb-3">
          Latest Posts ({data.recent_posts?.length || 0})
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {(data.recent_posts || []).map((post, index) => (
            <article
              key={postKey(post, index)}
              className="group relative rounded-xl overflow-hidden border border-gray-200 bg-white"
            >
              {post.thumbnail && !failedImages[postKey(post, index)] ? (
                <img
                  src={proxyUrl(post.thumbnail)}
                  alt={post.description || "Instagram post"}
                  className="w-full h-72 object-cover"
                  loading="lazy"
                  onError={() => {
                    const key = postKey(post, index);
                    setFailedImages((prev) => ({ ...prev, [key]: true }));
                  }}
                />
              ) : (
                <div className="w-full h-72 bg-gray-100 flex items-center justify-center text-sm text-gray-500">
                  Image unavailable
                </div>
              )}

              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/60 transition-colors duration-200" />

              <div className="absolute inset-x-0 bottom-0 p-4 text-white opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <div className="flex items-center gap-4 text-sm font-medium mb-2">
                  <span>❤ {fmt(post.likes)}</span>
                  <span>💬 {fmt(post.comments)}</span>
                  {post.views != null && (
                    <span>▶ {fmt(post.views)}</span>
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="uppercase tracking-wide bg-white/20 px-2 py-1 rounded">
                    {post.type || "Post"}
                  </span>
                  {post.url && (
                    <a
                      href={post.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline font-medium"
                    >
                      View on Instagram
                    </a>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>

        {(!data.recent_posts || data.recent_posts.length === 0) && (
          <p className="text-sm text-gray-500">No public posts found for this account.</p>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   Facebook Results – Identical to FacebookCompetitorAnalysis.jsx
   ══════════════════════════════════════════════════════════════════ */
function FacebookResults({ data }) {
  return (
    <div className="space-y-6">
      {/* Profile Card */}
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="flex flex-col sm:flex-row sm:items-center gap-5">
          {data.avatar ? (
            <img
              src={proxyUrl(data.avatar)}
              alt={data.display_name}
              className="w-20 h-20 rounded-full object-cover border border-gray-200"
            />
          ) : (
            <div className="w-20 h-20 rounded-full bg-gray-200" />
          )}

          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-lg font-bold text-gray-900">{data.display_name || data.username}</h3>
              {data.is_verified && (
                <span className="inline-flex items-center text-xs font-semibold text-blue-700 bg-blue-100 px-2 py-1 rounded-full">
                  Verified
                </span>
              )}
            </div>
            {data.username && <p className="text-sm text-gray-500">@{data.username}</p>}
            {data.category && <p className="text-sm text-gray-600 mt-1">{data.category}</p>}
            {(data.about || data.bio || data.description) && (
              <p className="text-sm text-gray-700 mt-2 whitespace-pre-wrap">
                {data.about || data.bio || data.description}
              </p>
            )}
            {data.page_url && (
              <a
                href={data.page_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block mt-2 text-sm text-blue-700 hover:underline"
              >
                Open Facebook Page
              </a>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6">
          <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
            <p className="text-xl font-bold text-gray-900">{fmt(data.followers)}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Followers</p>
          </div>
          <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
            <p className="text-xl font-bold text-gray-900">{fmt(data.fan_count || data.likes)}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Fans</p>
          </div>
          <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
            <p className="text-xl font-bold text-gray-900">{fmt(data.recent_posts?.length || 0)}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Recent Posts</p>
          </div>
          <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
            <p className="text-xl font-bold text-gray-900">{data.username || "-"}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Page ID</p>
          </div>
        </div>
      </div>

      {/* Latest Posts */}
      <div>
        <h3 className="text-base font-semibold text-gray-900 mb-3">
          Latest Posts ({data.recent_posts?.length || 0})
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {(data.recent_posts || []).map((post, i) => (
            <article
              key={post.id || post.url || `post-${i}`}
              className="group relative rounded-xl overflow-hidden border border-gray-200 bg-white"
            >
              {post.thumbnail ? (
                <img
                  src={proxyUrl(post.thumbnail)}
                  alt={post.description || "Facebook post"}
                  className="w-full h-64 object-cover"
                  loading="lazy"
                />
              ) : (
                <div className="w-full h-64 bg-gray-100 flex items-center justify-center text-sm text-gray-500">
                  No image
                </div>
              )}

              <div className="p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    {data.avatar ? (
                      <img
                        src={proxyUrl(data.avatar)}
                        alt={data.display_name || data.username || "Facebook page"}
                        className="h-8 w-8 rounded-full object-cover border border-gray-200"
                        loading="lazy"
                      />
                    ) : (
                      <div className="h-8 w-8 rounded-full bg-gray-200" />
                    )}
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold text-gray-800">
                        {data.display_name || data.username || "Facebook Page"}
                      </p>
                      {data.username && (
                        <p className="truncate text-[11px] text-gray-500">@{data.username}</p>
                      )}
                    </div>
                  </div>
                  <span className="inline-flex shrink-0 items-center rounded-full bg-blue-50 text-blue-700 border border-blue-200 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide">
                    {post.type || "post"}
                  </span>
                </div>
                <p className="text-sm text-gray-800 line-clamp-3 min-h-[3.6em]">
                  {post.description || "(no text)"}
                </p>
                <div className="mt-3 flex items-center gap-3 text-xs text-gray-500">
                  <span>👍 {fmt(post.likes)}</span>
                  <span>💬 {fmt(post.comments)}</span>
                  <span>↗ {fmt(post.shares)}</span>
                </div>
                <div className="mt-3 flex items-center justify-between text-xs">
                  <span className="text-gray-400">
                    {post.created_at ? new Date(post.created_at).toLocaleDateString() : "-"}
                  </span>
                  {post.url && (
                    <a
                      href={post.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-700 font-medium hover:underline"
                    >
                      View Post
                    </a>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>

        {(!data.recent_posts || data.recent_posts.length === 0) && (
          <p className="text-sm text-gray-500">No public posts available for this page.</p>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   Loading Skeletons – Platform-specific (identical to Apify pages)
   ══════════════════════════════════════════════════════════════════ */
function TikTokSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
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
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
            <div className="h-52 bg-gray-200 rounded" />
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
  );
}

function InstagramSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="bg-white border border-gray-200 rounded-xl p-6 flex items-center gap-4">
        <div className="w-20 h-20 rounded-full bg-gray-200" />
        <div className="flex-1 space-y-3">
          <div className="h-5 w-48 bg-gray-200 rounded" />
          <div className="h-4 w-80 bg-gray-200 rounded" />
          <div className="h-4 w-64 bg-gray-200 rounded" />
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="h-72 bg-gray-200 rounded-xl" />
        ))}
      </div>
      <p className="text-center text-sm text-gray-500">
        Scraping Instagram data, please wait… This may take 10–20 seconds.
      </p>
    </div>
  );
}

function FacebookSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      <div className="bg-white border border-gray-200 rounded-xl p-6 h-36" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-64 bg-gray-200 rounded-xl" />
        ))}
      </div>
      <p className="text-center text-sm text-gray-500">
        Scraping Facebook data, please wait… This may take 10–20 seconds.
      </p>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   Main Component
   ══════════════════════════════════════════════════════════════════ */
export default function ManualScraper() {
  const [platform, setPlatform] = useState("tiktok");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const handleAnalyze = async () => {
    const val = input.trim();
    if (!val) return;

    setLoading(true);
    setError(null);
    setData(null);

    try {
      const res = await fetch("/api/manual-scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform, username: val }),
      });
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.detail || "Request failed.");
      }

      if (json.status === "blocked_by_challenge") {
        setError(`⚠️ ${json.error_message || "Platform blocked the request with a captcha/login wall. Try again later."}`);
      } else if (json.status === "not_found") {
        setError("Profile not found. Double-check the username and try again.");
      } else if (json.status === "error") {
        setError(json.error_message || "An unknown error occurred.");
      } else {
        setData(json);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleAnalyze();
  };

  const selectedPlatform = PLATFORMS.find((p) => p.id === platform);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navigation */}
      <nav className="bg-white border-b border-gray-200 px-6 py-3">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <a href="/" className="text-sm text-gray-500 hover:text-gray-700 transition">
              ← Dashboard
            </a>
            <h1 className="text-lg font-semibold text-gray-900">Manual Scraper</h1>
          </div>
          <span className="text-xs bg-amber-100 text-amber-700 px-2 py-1 rounded-full font-medium">
            Playwright-powered
          </span>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* Header – matches Apify competitor analysis headers */}
        <div className="mb-6">
          <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            {platform === "tiktok" && (
              <svg className="w-6 h-6" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1v-3.5a6.37 6.37 0 00-.79-.05A6.34 6.34 0 003.15 15.2a6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.34-6.34V8.72a8.2 8.2 0 004.76 1.52V6.8a4.84 4.84 0 01-1-.11z" />
              </svg>
            )}
            {platform !== "tiktok" && <span>{selectedPlatform?.icon}</span>}
            {selectedPlatform?.label} Competitor Analysis
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Enter a {selectedPlatform?.label} username to scrape their public profile and recent{" "}
            {platform === "tiktok" ? "videos" : "posts"}.
          </p>
        </div>

        {/* Search Bar – matches Apify style */}
        <div className="flex gap-3 mb-6">
          {/* Platform selector */}
          <div className="flex gap-1">
            {PLATFORMS.map((p) => (
              <button
                key={p.id}
                onClick={() => { setPlatform(p.id); setData(null); setError(null); }}
                className={`px-3 py-2.5 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5 ${
                  platform === p.id
                    ? "bg-gray-900 text-white shadow-md"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                <span>{p.icon}</span>
                <span className="hidden sm:inline">{p.label}</span>
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="relative flex-1">
            <span className="absolute inset-y-0 left-3 flex items-center text-gray-400 pointer-events-none select-none">
              @
            </span>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={platform === "facebook" ? "nike or facebook.com/..." : "username"}
              className="w-full pl-8 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gray-900 focus:border-gray-900 outline-none transition"
              disabled={loading}
            />
          </div>

          <button
            onClick={handleAnalyze}
            disabled={loading || !input.trim()}
            className="px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-black disabled:opacity-50 transition flex items-center gap-2"
          >
            {loading ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Analyzing…
              </>
            ) : (
              "Analyze"
            )}
          </button>
        </div>

        {/* Loading Skeleton – platform-specific */}
        {loading && platform === "tiktok" && <TikTokSkeleton />}
        {loading && platform === "instagram" && <InstagramSkeleton />}
        {loading && platform === "facebook" && <FacebookSkeleton />}

        {/* Error Banner – matches Apify style */}
        {error && !loading && (
          <div className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg text-sm mb-6">
            <svg className="w-5 h-5 shrink-0 mt-0.5 text-red-500" fill="currentColor" viewBox="0 0 20 20">
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

        {/* Results – Platform-specific identical layouts */}
        {data && !loading && platform === "tiktok" && <TikTokResults data={data} />}
        {data && !loading && platform === "instagram" && <InstagramResults data={data} />}
        {data && !loading && platform === "facebook" && <FacebookResults data={data} />}

        {/* Empty State */}
        {!data && !loading && !error && (
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-12 text-center">
            <div className="text-5xl mb-4">🔍</div>
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Ready to Analyze</h3>
            <p className="text-sm text-gray-500 max-w-md mx-auto">
              Select a platform, enter a username or full profile URL, and click "Analyze" to fetch
              public profile data using Playwright.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2 text-xs text-gray-400">
              <span className="bg-gray-100 px-3 py-1 rounded-full">No API keys needed</span>
              <span className="bg-gray-100 px-3 py-1 rounded-full">Anti-detection stealth</span>
              <span className="bg-gray-100 px-3 py-1 rounded-full">Same data as Apify</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
