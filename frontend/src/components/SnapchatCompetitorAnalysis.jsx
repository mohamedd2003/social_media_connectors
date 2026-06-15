import { useState } from "react";

export default function SnapchatCompetitorAnalysis({ backendUrl = "" }) {
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const fmt = (n) => {
    if (n == null) return "-";
    if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return Number(n).toLocaleString();
  };

  const normalize = (value) => {
    const clean = (value || "").trim();
    if (!clean) return "";

    if (!clean.startsWith("http")) return clean.replace(/^@/, "");

    try {
      const u = new URL(clean);
      const parts = u.pathname.split("/").filter(Boolean);
      if (parts[0] === "add" && parts[1]) return parts[1].replace(/^@/, "");
      if (parts[0]) return parts[0].replace(/^@/, "");
      return clean;
    } catch {
      return clean;
    }
  };

  const analyze = async () => {
    const clean = normalize(username);
    if (!clean) return;

    setLoading(true);
    setError(null);
    setData(null);

    try {
      const res = await fetch(
        `${backendUrl}/api/v1/snapchat/competitor/${encodeURIComponent(clean)}`
      );
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json.detail || "Failed to fetch Snapchat competitor data.");
      }
      setData(json);
    } catch (err) {
      setError(err.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="mt-10 pt-8 border-t border-gray-200">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-gray-900">Snapchat Competitor Analysis</h2>
        <p className="text-sm text-gray-500 mt-1">
          Analyze a public Snapchat profile by username or profile URL using Apify.
        </p>
      </div>

      <div className="flex gap-3 mb-6">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && analyze()}
          placeholder="snapchat or https://www.snapchat.com/add/snapchat"
          className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-yellow-500 focus:border-yellow-500 outline-none"
          disabled={loading}
        />
        <button
          onClick={analyze}
          disabled={loading || !username.trim()}
          className="px-5 py-2.5 bg-yellow-400 text-gray-900 rounded-lg text-sm font-semibold hover:bg-yellow-500 transition disabled:opacity-60"
        >
          {loading ? "Analyzing..." : "Analyze"}
        </button>
      </div>

      {loading && (
        <div className="space-y-5 animate-pulse">
          <div className="bg-white border border-gray-200 rounded-xl p-6 h-36" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-64 bg-gray-200 rounded-xl" />
            ))}
          </div>
        </div>
      )}

      {error && !loading && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <p className="font-semibold">Analysis failed</p>
          <p className="mt-1">{error}</p>
        </div>
      )}

      {data && !loading && (
        <div className="space-y-6">
          <div className="bg-white border border-gray-200 rounded-xl p-6">
            <div className="flex flex-col sm:flex-row sm:items-center gap-5">
              {data.profilePicture ? (
                <img
                  src={data.profilePicture}
                  alt={data.displayName || data.username}
                  className="w-20 h-20 rounded-full object-cover border border-gray-200"
                />
              ) : (
                <div className="w-20 h-20 rounded-full bg-yellow-100 flex items-center justify-center text-3xl">
                  👻
                </div>
              )}

              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-lg font-bold text-gray-900">
                    {data.displayName || data.username || "Snapchat"}
                  </h3>
                  {data.isVerified && (
                    <span className="inline-flex items-center text-xs font-semibold text-blue-700 bg-blue-100 px-2 py-1 rounded-full">
                      Verified
                    </span>
                  )}
                </div>
                {data.username && <p className="text-sm text-gray-500">@{data.username}</p>}
                {data.bio && <p className="text-sm text-gray-700 mt-2 whitespace-pre-wrap">{data.bio}</p>}
                {data.profileUrl && (
                  <a
                    href={data.profileUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-block mt-2 text-sm text-blue-700 hover:underline"
                  >
                    Open Snapchat Profile
                  </a>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6">
              <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
                <p className="text-xl font-bold text-gray-900">{fmt(data.followersCount)}</p>
                <p className="text-xs text-gray-500 uppercase tracking-wide">Followers</p>
              </div>
              <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
                <p className="text-xl font-bold text-gray-900">{fmt(data.friendsCount)}</p>
                <p className="text-xs text-gray-500 uppercase tracking-wide">Friends</p>
              </div>
              <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
                <p className="text-xl font-bold text-gray-900">{fmt(data.snapScore)}</p>
                <p className="text-xs text-gray-500 uppercase tracking-wide">Snap Score</p>
              </div>
              <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
                <p className="text-xl font-bold text-gray-900">{fmt(data.latestPosts?.length || 0)}</p>
                <p className="text-xs text-gray-500 uppercase tracking-wide">Recent Posts</p>
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-base font-semibold text-gray-900 mb-3">
              Latest Posts ({data.latestPosts?.length || 0})
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {(data.latestPosts || []).map((post, index) => (
                <article
                  key={post.id || post.url || `snap-post-${index}`}
                  className="group relative rounded-xl overflow-hidden border border-gray-200 bg-white"
                >
                  {post.imageUrl ? (
                    <img
                      src={post.imageUrl}
                      alt={post.caption || "Snapchat post"}
                      className="w-full h-64 object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="w-full h-64 bg-gray-100 flex items-center justify-center text-sm text-gray-500">
                      No image
                    </div>
                  )}

                  <div className="p-4">
                    <p className="text-sm text-gray-800 line-clamp-3 min-h-[3.6em]">
                      {post.caption || "(no text)"}
                    </p>
                    <div className="mt-3 flex items-center gap-3 text-xs text-gray-500">
                      <span>👁 {fmt(post.viewCount)}</span>
                      <span>💬 {fmt(post.commentCount)}</span>
                      <span>↗ {fmt(post.shareCount)}</span>
                    </div>
                    <div className="mt-3 flex items-center justify-between text-xs">
                      <span className="text-gray-400">
                        {post.createdTime ? new Date(post.createdTime).toLocaleDateString() : "-"}
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

            {(!data.latestPosts || data.latestPosts.length === 0) && (
              <p className="text-sm text-gray-500">No public posts available for this profile.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
