import { useState } from "react";

export default function InstagramCompetitorAnalysis({ backendUrl = "" }) {
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [failedImages, setFailedImages] = useState({});

  const fmt = (n) => {
    if (n == null) return "-";
    if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return Number(n).toLocaleString();
  };

  const analyze = async () => {
    const clean = username.trim().replace(/^@/, "");
    if (!clean) return;

    setLoading(true);
    setError(null);
    setData(null);
    setFailedImages({});

    try {
      const res = await fetch(
        `${backendUrl}/api/v1/instagram/competitor/${encodeURIComponent(clean)}`
      );
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json.detail || "Failed to fetch Instagram competitor data.");
      }
      setData(json);
    } catch (err) {
      setError(err.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const onEnter = (e) => {
    if (e.key === "Enter") analyze();
  };

  const imageProxyUrl = (rawUrl) => {
    if (!rawUrl) return "";
    return `${backendUrl}/api/v1/instagram/media/proxy?url=${encodeURIComponent(rawUrl)}`;
  };

  const postKey = (post, index) => post.id || post.url || `post-${index}`;

  return (
    <section className="mt-10 pt-8 border-t border-gray-200">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-gray-900">Instagram Competitor Analysis</h2>
        <p className="text-sm text-gray-500 mt-1">
          Analyze a public Instagram profile and its latest posts using Apify.
        </p>
      </div>

      <div className="flex gap-3 mb-6">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={onEnter}
          placeholder="instagram"
          className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-pink-500 focus:border-pink-500 outline-none"
          disabled={loading}
        />
        <button
          onClick={analyze}
          disabled={loading || !username.trim()}
          className="px-5 py-2.5 bg-gradient-to-r from-pink-500 via-rose-500 to-orange-500 text-white rounded-lg text-sm font-medium hover:opacity-90 transition disabled:opacity-60"
        >
          {loading ? "Analyzing..." : "Analyze"}
        </button>
      </div>

      {loading && (
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
            Scraping Instagram data, please wait... This may take 10-20 seconds.
          </p>
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
              {data.profilePicUrl ? (
                <img
                  src={data.profilePicUrl}
                  alt={data.fullName || data.username}
                  className="w-20 h-20 rounded-full object-cover border border-gray-200"
                />
              ) : (
                <div className="w-20 h-20 rounded-full bg-gray-200" />
              )}

              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-lg font-bold text-gray-900">
                    {data.fullName || data.username}
                  </h3>
                  {data.isVerified && (
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
                {data.biography && (
                  <p className="text-sm text-gray-700 mt-2 whitespace-pre-wrap">{data.biography}</p>
                )}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 mt-6">
              <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
                <p className="text-xl font-bold text-gray-900">{fmt(data.followersCount)}</p>
                <p className="text-xs text-gray-500 uppercase tracking-wide">Followers</p>
              </div>
              <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
                <p className="text-xl font-bold text-gray-900">{fmt(data.followsCount)}</p>
                <p className="text-xs text-gray-500 uppercase tracking-wide">Following</p>
              </div>
              <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-center">
                <p className="text-xl font-bold text-gray-900">{fmt(data.postsCount)}</p>
                <p className="text-xs text-gray-500 uppercase tracking-wide">Total Posts</p>
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
                  key={postKey(post, index)}
                  className="group relative rounded-xl overflow-hidden border border-gray-200 bg-white"
                >
                  {post.displayUrl && !failedImages[postKey(post, index)] ? (
                    <img
                      src={imageProxyUrl(post.displayUrl)}
                      alt={post.caption || "Instagram post"}
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
                      <span>❤ {fmt(post.likeCount)}</span>
                      <span>💬 {fmt(post.commentCount)}</span>
                      {post.videoViewCount !== null && post.videoViewCount !== undefined && (
                        <span>▶ {fmt(post.videoViewCount)}</span>
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

            {(!data.latestPosts || data.latestPosts.length === 0) && (
              <p className="text-sm text-gray-500">No public posts found for this account.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
