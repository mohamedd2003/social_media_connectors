import { useState, useEffect, useCallback } from "react";

/**
 * SnapchatDashboard – Matches the Snapchat Creator/Business Portal layout:
 * - Profile Details header (name, handle, avatar, profile type)
 * - Overview Metrics (Followers, Reach, Views with 28-day comparison)
 * - Content tabs (Public Stories, Saved Stories, Spotlight)
 */
export default function SnapchatDashboard({ accountId, backendUrl = "" }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Aggregated overview data from /snap/profile/overview
  const [overview, setOverview] = useState(null);

  // Ads insights from /api/v1/snapchat/ads-insights
  const [adsInsights, setAdsInsights] = useState(null);
  const [apiBlocked, setApiBlocked] = useState(false);

  // Active content tab
  const [contentTab, setContentTab] = useState("public");

  // Manual metrics (localStorage fallback when API is unavailable)
  const [manualMetrics, setManualMetrics] = useState({
    followers: "",
    reach: "",
    views: "",
  });
  const [hasManualMetrics, setHasManualMetrics] = useState(false);
  const [editingMetrics, setEditingMetrics] = useState(false);
  const [deleting, setDeleting] = useState(null); // media_id being deleted

  // ── Data fetching ──────────────────────────────────────────────────

  const fetchOverview = useCallback(async () => {
    if (!accountId) return;
    setLoading(true);
    setError(null);
    setApiBlocked(false);
    try {
      const res = await fetch(
        `${backendUrl}/snap/profile/overview?account_id=${accountId}`
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load profile");
      setOverview(data);
    } catch (err) {
      if (err.message?.includes("DNS")) {
        setApiBlocked(true);
      }
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [accountId, backendUrl]);

  const fetchAdsInsights = useCallback(async () => {
    if (!accountId) return;
    try {
      const res = await fetch(
        `${backendUrl}/api/v1/snapchat/ads-insights/${accountId}?account_id=${accountId}`
      );
      if (res.ok) {
        const data = await res.json();
        setAdsInsights(data);
      }
    } catch {
      // Non-critical — ads insights are optional
    }
  }, [accountId, backendUrl]);

  useEffect(() => {
    fetchOverview();
    fetchAdsInsights();
  }, [fetchOverview, fetchAdsInsights]);

  // Load manual metrics from backend DB
  useEffect(() => {
    if (!accountId) return;
    (async () => {
      try {
        const res = await fetch(
          `${backendUrl}/snap/manual-metrics?account_id=${accountId}`
        );
        if (res.ok) {
          const data = await res.json();
          setManualMetrics({
            followers: data.followers || "",
            reach: data.reach || "",
            views: data.views || "",
          });
          setHasManualMetrics(Boolean(data.updated_at));
        }
      } catch {
        // Fallback: load from localStorage (migration)
        try {
          const raw = localStorage.getItem(`snap_manual_metrics_${accountId}`);
          if (raw) {
            const parsed = JSON.parse(raw);
            setManualMetrics({
              followers: parsed?.followers ?? "",
              reach: parsed?.reach ?? "",
              views: parsed?.views ?? "",
            });
            setHasManualMetrics(true);
          }
        } catch {
          /* ignore */
        }
      }
    })();
  }, [accountId, backendUrl]);

  // Save manual metrics to backend DB (and localStorage as fallback)
  const saveManualMetrics = useCallback(async () => {
    if (!accountId) return;
    const f = Number(manualMetrics.followers) || 0;
    const r = Number(manualMetrics.reach) || 0;
    const v = Number(manualMetrics.views) || 0;
    // Save to localStorage as fallback
    localStorage.setItem(
      `snap_manual_metrics_${accountId}`,
      JSON.stringify(manualMetrics)
    );
    // Save to backend DB
    try {
      await fetch(
        `${backendUrl}/snap/manual-metrics?account_id=${accountId}&followers=${f}&reach=${r}&views=${v}`,
        { method: "PUT" }
      );
    } catch {
      /* localStorage fallback already saved */
    }
    setHasManualMetrics(true);
    setEditingMetrics(false);
    // Refresh overview to merge new manual metrics
    fetchOverview();
  }, [accountId, backendUrl, manualMetrics, fetchOverview]);

  async function handleDeleteMedia(mediaId) {
    if (!confirm("Delete this media? This cannot be undone.")) return;
    setDeleting(mediaId);
    try {
      const res = await fetch(
        `${backendUrl}/snap/media/${mediaId}?account_id=${accountId}`,
        { method: "DELETE" }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Delete failed");
      // Refresh data
      fetchOverview();
    } catch (err) {
      setError(`Delete failed: ${err.message}`);
    } finally {
      setDeleting(null);
    }
  }

  async function handleRefreshToken() {
    try {
      const formData = new FormData();
      formData.append("account_id", accountId);
      const res = await fetch(`${backendUrl}/snap/auth/refresh`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || "Refresh failed");
      }
      fetchOverview();
    } catch (err) {
      setError(`Token refresh failed: ${err.message}`);
    }
  }

  if (!accountId) return null;

  // ── Derive display values ──────────────────────────────────────────

  const profile = overview?.profile || {};
  const metrics = overview?.metrics || {};
  const publicStories = overview?.public_stories || [];
  const savedStories = overview?.saved_stories || [];
  const spotlight = overview?.spotlight || [];

  // When manual metrics exist, prioritize them for display.
  const displayFollowers = hasManualMetrics
    ? Number(manualMetrics.followers) || 0
    : metrics.total_followers?.current || 0;
  const displayReach = hasManualMetrics
    ? Number(manualMetrics.reach) || 0
    : metrics.total_reach?.current || 0;
  const displayViews = hasManualMetrics
    ? Number(manualMetrics.views) || 0
    : metrics.profile_views?.current || 0;

  const followersPct = metrics.total_followers?.change_pct;
  const reachPct = metrics.total_reach?.change_pct;

  const contentTabs = [
    { key: "public", label: "Public Stories", count: publicStories.length },
    { key: "saved", label: "Saved Stories", count: savedStories.length },
    { key: "spotlight", label: "Spotlight", count: spotlight.length },
    ...(adsInsights?.campaigns?.length
      ? [{ key: "ads", label: "Campaigns", count: adsInsights.campaigns.length }]
      : []),
  ];

  const activeContent =
    contentTab === "public"
      ? publicStories
      : contentTab === "saved"
      ? savedStories
      : contentTab === "ads"
      ? (adsInsights?.campaigns || []).map((c) => ({
          id: c.campaign_id,
          name: c.campaign_name,
          status: c.status,
          type: "CAMPAIGN",
          created_at: c.start_time,
          objective: c.objective,
          impressions: c.totals?.impressions,
          swipes: c.totals?.swipes,
          spend: c.totals?.spend,
          source: "campaign",
        }))
      : spotlight;

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* ─── Top bar ───────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-yellow-400 flex items-center justify-center">
            <svg className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 15l-5-5 1.41-1.41L11 14.17l7.59-7.59L20 8l-9 9z" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-gray-900">
            Snapchat Public Profile
          </h2>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleRefreshToken}
            className="text-xs text-gray-500 hover:text-gray-800 underline"
          >
            Refresh Token
          </button>
          {!overview?.api_available && (
            <a
              href={`${backendUrl}/snap/auth/login`}
              className="text-xs text-yellow-700 bg-yellow-100 hover:bg-yellow-200 px-2 py-1 rounded-full font-medium transition"
            >
              🔑 Re-authenticate with Profile API
            </a>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center justify-between">
          <p className="text-sm text-red-700">{error}</p>
          <button onClick={fetchOverview} className="text-xs text-red-600 underline ml-4">
            Retry
          </button>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-400"></div>
          <span className="ml-3 text-gray-500 text-sm">Loading profile...</span>
        </div>
      )}

      {!loading && overview && (
        <>
          {/* ═══ Profile Header (matches screenshot) ═══════════════════ */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            {/* Yellow accent bar */}
            <div className="h-1.5 bg-yellow-400"></div>
            <div className="p-6">
              <div className="flex items-start gap-5">
                {/* Avatar / Bitmoji */}
                <div className="flex-shrink-0">
                  {profile.avatar_url ? (
                    <img
                      src={profile.avatar_url}
                      alt="Profile"
                      className="w-20 h-20 rounded-full object-cover border-2 border-yellow-300"
                    />
                  ) : (
                    <div className="w-20 h-20 rounded-full bg-gradient-to-br from-yellow-300 to-yellow-500 flex items-center justify-center border-2 border-yellow-300">
                      <span className="text-3xl">👻</span>
                    </div>
                  )}
                </div>
                {/* Profile Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-xl font-bold text-gray-900">
                      {profile.display_name || profile.organization_name || "Snapchat User"}
                    </h3>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                      {profile.profile_tier === "TIER_PUBLIC" ? "Public Profile" : profile.profile_type}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 mt-1">
                    @{profile.snap_user_name || profile.username || profile.email?.split("@")[0] || "—"}
                    {profile.email && (
                      <span className="ml-2 text-gray-400">· {profile.email}</span>
                    )}
                  </p>
                  {profile.organization_name && (
                    <p className="text-xs text-gray-400 mt-1">
                      {profile.organization_name} · Organization Admin
                    </p>
                  )}
                  {/* Action buttons matching screenshot */}
                  <div className="flex flex-wrap gap-2 mt-3">
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700 border border-gray-200">
                      👤 Actor Needed
                    </span>
                    <a
                      href="https://profile.snapchat.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 transition"
                    >
                      Edit Profile
                    </a>
                    <a
                      href="https://business.snapchat.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-yellow-400 text-gray-900 hover:bg-yellow-500 transition"
                    >
                      Promote Your Profile
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ═══ Overview Metrics (Followers / Reach / Views) ══════════ */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-semibold text-gray-900">Overview</h3>
                {hasManualMetrics && !editingMetrics && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full border border-blue-200 text-blue-700 bg-blue-50">
                    Manual values
                  </span>
                )}
              </div>
              {editingMetrics ? (
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setEditingMetrics(false)}
                    className="text-xs text-gray-500 hover:text-gray-700 underline"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={saveManualMetrics}
                    className="text-xs text-blue-600 hover:text-blue-800 underline"
                  >
                    Save Metrics
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setEditingMetrics(true)}
                  className="text-xs text-blue-600 hover:text-blue-800 underline"
                >
                  Edit Manual Metrics
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Total Followers */}
              <MetricCard
                label="Total Followers"
                value={displayFollowers}
                changePct={followersPct}
                editing={editingMetrics}
                manualValue={manualMetrics.followers}
                onManualChange={(v) =>
                  setManualMetrics((p) => ({ ...p, followers: v }))
                }
              />
              {/* Total Reach */}
              <MetricCard
                label="Total Reach"
                value={displayReach}
                changePct={reachPct}
                editing={editingMetrics}
                manualValue={manualMetrics.reach}
                onManualChange={(v) =>
                  setManualMetrics((p) => ({ ...p, reach: v }))
                }
              />
              {/* Profile Views */}
              <MetricCard
                label="Profile Views"
                value={displayViews}
                changePct={null}
                editing={editingMetrics}
                manualValue={manualMetrics.views}
                onManualChange={(v) =>
                  setManualMetrics((p) => ({ ...p, views: v }))
                }
              />
              {/* Returning Viewers */}
              <MetricCard
                label="Returning Viewers"
                value={0}
                changePct={null}
              />
            </div>

            {overview.error && !editingMetrics && (
              <p className="text-xs text-amber-600 mt-3 flex items-center gap-1">
                <span>⚠️</span>
                {overview.error}
              </p>
            )}
          </div>

          {/* ═══ Content Tabs (Public Stories / Saved Stories / Spotlight) ═ */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            {/* Tab bar */}
            <div className="border-b border-gray-200 px-6 pt-4">
              <nav className="flex gap-1">
                {contentTabs.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setContentTab(t.key)}
                    className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
                      contentTab === t.key
                        ? "bg-white border border-b-white border-gray-200 text-gray-900 -mb-px"
                        : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    {t.label}
                    <span className="ml-1.5 text-xs text-gray-400">
                      ({t.count})
                    </span>
                  </button>
                ))}
              </nav>
            </div>

            {/* Content grid */}
            <div className="p-6">
              {activeContent.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {activeContent.map((item) => (
                    <ContentCard
                      key={item.id}
                      item={item}
                      tab={contentTab}
                      onDelete={contentTab === "saved" ? handleDeleteMedia : null}
                      deleting={deleting}
                    />
                  ))}
                </div>
              ) : (
                <EmptyState tab={contentTab} />
              )}
            </div>
          </div>

          {/* ═══ Ads Performance Summary ═════════════════════════════ */}
          {adsInsights && (
            <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
              <h3 className="text-base font-semibold text-gray-900 mb-4">
                Ads Performance
                <span className="ml-2 text-xs text-gray-400 font-normal">
                  {adsInsights.start_date} → {adsInsights.end_date}
                </span>
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="bg-gray-50 rounded-lg p-4 text-center">
                  <p className="text-xs text-gray-500 mb-1">Impressions</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {adsInsights.total_impressions.toLocaleString()}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4 text-center">
                  <p className="text-xs text-gray-500 mb-1">Swipe-Ups</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {adsInsights.total_swipes.toLocaleString()}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4 text-center">
                  <p className="text-xs text-gray-500 mb-1">Spend</p>
                  <p className="text-2xl font-bold text-gray-900">
                    ${adsInsights.total_spend.toFixed(2)}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4 text-center">
                  <p className="text-xs text-gray-500 mb-1">Conversions</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {adsInsights.total_conversions.toLocaleString()}
                  </p>
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-3">
                {adsInsights.ad_account_name} · {adsInsights.currency} · {adsInsights.campaigns.length} campaign(s)
              </p>
            </div>
          )}

          {/* ═══ Data Source Summary ═══════════════════════════════════ */}
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
              <span className="font-medium text-gray-700">Data Sources:</span>
              <span className="bg-white border border-gray-200 px-2 py-0.5 rounded-full">
                Media Files: {overview.media_count}
              </span>
              <span className="bg-white border border-gray-200 px-2 py-0.5 rounded-full">
                Campaigns: {overview.campaigns_count}
              </span>
              <span
                className={`px-2 py-0.5 rounded-full ${
                  overview.api_available
                    ? "bg-green-50 border border-green-200 text-green-700"
                    : "bg-amber-50 border border-amber-200 text-amber-700"
                }`}
              >
                Public Profile API:{" "}
                {overview.api_available ? "Connected" : "Unavailable"}
              </span>
            </div>
            {overview.error && (
              <p className="text-xs text-amber-600 mt-2">{overview.error}</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/* Sub-components                                                            */
/* ═══════════════════════════════════════════════════════════════════════════ */

function MetricCard({
  label,
  value,
  changePct,
  editing,
  manualValue,
  onManualChange,
}) {
  return (
    <div className="bg-gray-50 rounded-xl p-5 text-center border border-gray-100">
      <p className="text-sm text-gray-500 mb-2">{label}</p>
      {editing ? (
        <input
          type="number"
          min="0"
          value={manualValue}
          onChange={(e) => onManualChange(e.target.value)}
          placeholder="0"
          className="w-24 mx-auto block text-center text-2xl font-bold text-gray-900 border border-gray-300 rounded-lg px-2 py-1 focus:ring-2 focus:ring-yellow-400 focus:border-yellow-400"
        />
      ) : (
        <p className="text-3xl font-bold text-gray-900">
          {Number(value).toLocaleString()}
        </p>
      )}
      {/* 28-day comparison badge */}
      <div className="mt-2 flex items-center justify-center gap-1">
        {changePct != null ? (
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
              changePct >= 0
                ? "bg-green-100 text-green-700"
                : "bg-red-100 text-red-700"
            }`}
          >
            {changePct >= 0 ? "↑" : "↓"}{" "}
            {Math.abs(changePct).toFixed(1)}%
          </span>
        ) : (
          <span className="text-xs text-gray-400">vs. previous 28 days</span>
        )}
      </div>
    </div>
  );
}

function ContentCard({ item, tab, onDelete, deleting }) {
  const mediaUrl = item.download_link || item.media_url || item.thumbnail_url;
  const isVideo = item.type === "VIDEO" || tab === "spotlight";
  const isDeleting = deleting === item.id;
  const isCampaign = item.source === "campaign";

  if (isCampaign) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow p-4 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-gray-900 truncate flex-1">
            {item.name || "(untitled)"}
          </p>
          {item.status && (
            <span
              className={`ml-2 text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${
                item.status === "ACTIVE"
                  ? "bg-green-100 text-green-700"
                  : "bg-gray-100 text-gray-600"
              }`}
            >
              {item.status}
            </span>
          )}
        </div>
        {item.objective && (
          <p className="text-xs text-gray-500">Objective: {item.objective}</p>
        )}
        <div className="grid grid-cols-3 gap-2 mt-2">
          <div className="text-center bg-gray-50 rounded-lg p-2">
            <p className="text-xs text-gray-500">Impressions</p>
            <p className="text-sm font-semibold text-gray-900">
              {(item.impressions || 0).toLocaleString()}
            </p>
          </div>
          <div className="text-center bg-gray-50 rounded-lg p-2">
            <p className="text-xs text-gray-500">Swipes</p>
            <p className="text-sm font-semibold text-gray-900">
              {(item.swipes || 0).toLocaleString()}
            </p>
          </div>
          <div className="text-center bg-gray-50 rounded-lg p-2">
            <p className="text-xs text-gray-500">Spend</p>
            <p className="text-sm font-semibold text-gray-900">
              ${(item.spend || 0).toFixed(2)}
            </p>
          </div>
        </div>
        {item.created_at && (
          <p className="text-xs text-gray-400">
            Started: {new Date(item.created_at).toLocaleDateString()}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className={`bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow ${isDeleting ? "opacity-50" : ""}`}>
      {/* Media preview */}
      {mediaUrl && !isVideo && (
        <img
          src={mediaUrl}
          alt={item.name || "Story"}
          className="w-full h-48 object-cover bg-gray-100"
        />
      )}
      {mediaUrl && isVideo && (
        <video
          src={mediaUrl}
          className="w-full h-48 object-cover bg-gray-100"
          controls
          muted
        />
      )}
      {!mediaUrl && (
        <div className="w-full h-48 bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center">
          <span className="text-4xl opacity-40">👻</span>
        </div>
      )}

      {/* Info */}
      <div className="p-4 space-y-1.5">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-gray-900 truncate flex-1">
            {item.name || "(untitled)"}
          </p>
          {item.status && (
            <span
              className={`ml-2 text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${
                item.status === "READY" || item.status === "ACTIVE"
                  ? "bg-green-100 text-green-700"
                  : "bg-gray-100 text-gray-600"
              }`}
            >
              {item.status}
            </span>
          )}
        </div>

        {item.type && (
          <p className="text-xs text-gray-500">{item.type}</p>
        )}

        {(item.width_px || item.height_px) && (
          <p className="text-xs text-gray-500">
            {item.width_px || "?"}×{item.height_px || "?"} px
          </p>
        )}

        {item.file_size_in_bytes != null && (
          <p className="text-xs text-gray-500">
            {(item.file_size_in_bytes / 1024).toFixed(1)} KB
          </p>
        )}

        {item.view_count != null && (
          <p className="text-xs text-gray-500">
            {item.view_count.toLocaleString()} views
          </p>
        )}

        {item.profile_name && (
          <p className="text-xs text-gray-400">
            Profile: {item.profile_name}
          </p>
        )}

        {item.source === "media" && (
          <p className="text-xs text-blue-500">Ad Account Media</p>
        )}

        <p className="text-xs text-gray-400">
          {item.created_at
            ? new Date(item.created_at).toLocaleString()
            : ""}
        </p>

        {mediaUrl && (
          <a
            href={mediaUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline inline-block mt-1"
          >
            Open Full Size
          </a>
        )}

        {onDelete && (
          <button
            onClick={() => onDelete(item.id)}
            disabled={isDeleting}
            className="mt-2 w-full text-xs text-red-600 bg-red-50 hover:bg-red-100 border border-red-200 rounded-lg px-3 py-1.5 transition disabled:opacity-50"
          >
            {isDeleting ? "Deleting..." : "🗑 Delete"}
          </button>
        )}
      </div>
    </div>
  );
}

function EmptyState({ tab }) {
  const messages = {
    public:
      "No Public Stories found. Post stories via the Snapchat app or business.snapchat.com.",
    saved:
      "No Saved Stories / Media found in this ad account.",
    spotlight:
      "No Spotlight posts found from the Public Profile.",
    ads:
      "No ad campaigns found. Create a campaign via business.snapchat.com or the API.",
  };

  return (
    <div className="text-center py-12">
      <span className="text-4xl mb-3 block opacity-40">👻</span>
      <p className="text-sm text-gray-500">{messages[tab]}</p>
    </div>
  );
}
