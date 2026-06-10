import { useState, useEffect, useCallback } from "react";

/**
 * SnapchatDashboard – Displays Snapchat ad insights and
 * provides a paid-ad creation form, mirroring the existing
 * FB/IG insights table but with Snapchat-specific metrics.
 */
export default function SnapchatDashboard({ accountId, backendUrl = "" }) {
  const [insights, setInsights] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Ad creation state
  const [selectedCampaign, setSelectedCampaign] = useState("");
  const [adMessage, setAdMessage] = useState("");
  const [adImage, setAdImage] = useState(null);
  const [creating, setCreating] = useState(false);
  const [createStatus, setCreateStatus] = useState(null);

  const fetchInsights = useCallback(async () => {
    if (!accountId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${backendUrl}/snap/insights?account_id=${accountId}`
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to fetch insights");
      setInsights(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
      setInsights([]);
    } finally {
      setLoading(false);
    }
  }, [accountId, backendUrl]);

  const fetchCampaigns = useCallback(async () => {
    if (!accountId) return;
    try {
      const res = await fetch(
        `${backendUrl}/snap/campaigns?account_id=${accountId}`
      );
      const data = await res.json();
      if (res.ok && Array.isArray(data)) {
        setCampaigns(data);
        if (data.length > 0) setSelectedCampaign(data[0].id);
      }
    } catch {
      /* campaigns are optional for the view */
    }
  }, [accountId, backendUrl]);

  useEffect(() => {
    fetchInsights();
    fetchCampaigns();
  }, [fetchInsights, fetchCampaigns]);

  async function handleCreateAd(e) {
    e.preventDefault();
    if (!adMessage.trim() || !selectedCampaign || !adImage) return;

    setCreating(true);
    setCreateStatus(null);
    try {
      const formData = new FormData();
      formData.append("account_id", accountId);
      formData.append("campaign_id", selectedCampaign);
      formData.append("message", adMessage);
      formData.append("images", adImage);

      const res = await fetch(`${backendUrl}/snap/ads/create`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create ad");

      setCreateStatus({ type: "success", message: "Ad created (PAUSED)!" });
      setAdMessage("");
      setAdImage(null);
      fetchInsights();
    } catch (err) {
      setCreateStatus({ type: "error", message: err.message });
    } finally {
      setCreating(false);
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
      fetchInsights();
    } catch (err) {
      setError(`Token refresh failed: ${err.message}`);
    }
  }

  if (!accountId) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">
          Snapchat Ad Insights
        </h2>
        <button
          onClick={handleRefreshToken}
          className="text-xs text-blue-600 hover:text-blue-800 underline"
        >
          Refresh Token
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 rounded p-3">{error}</p>
      )}

      {/* Create Ad Form */}
      {campaigns.length > 0 && (
        <div className="bg-white p-5 border border-gray-200 rounded-lg shadow-sm">
          <h3 className="text-md font-semibold text-gray-800 mb-3">
            Create Paid Ad
          </h3>
          <form onSubmit={handleCreateAd} className="space-y-3">
            <select
              value={selectedCampaign}
              onChange={(e) => setSelectedCampaign(e.target.value)}
              className="block w-full max-w-xs border border-gray-300 rounded-lg px-3 py-2 text-sm"
              disabled={creating}
            >
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.status})
                </option>
              ))}
            </select>
            <textarea
              value={adMessage}
              onChange={(e) => setAdMessage(e.target.value)}
              placeholder="Ad headline / copy"
              className="w-full border border-gray-300 rounded-lg p-3 text-sm min-h-[80px]"
              disabled={creating}
            />
            <input
              type="file"
              accept="image/*,video/*"
              onChange={(e) => setAdImage(e.target.files[0] || null)}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-yellow-50 file:text-yellow-700 hover:file:bg-yellow-100"
              disabled={creating}
            />
            <div className="flex items-center justify-between">
              {createStatus && (
                <span
                  className={`text-sm ${
                    createStatus.type === "success"
                      ? "text-green-600"
                      : "text-red-600"
                  }`}
                >
                  {createStatus.message}
                </span>
              )}
              <button
                type="submit"
                disabled={creating || !adMessage.trim() || !adImage}
                className="bg-yellow-400 text-gray-900 px-5 py-2 rounded-lg text-sm font-semibold hover:bg-yellow-500 disabled:opacity-50 transition"
              >
                {creating ? "Creating..." : "Create Ad"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Insights Table */}
      {loading && (
        <p className="text-gray-500 text-sm">Loading Snapchat insights...</p>
      )}

      {!loading && insights.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white border border-gray-200 rounded-lg overflow-hidden">
            <thead className="bg-yellow-50">
              <tr>
                <th className="text-left text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Ad
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Impressions
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Swipes
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Spend
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Conversions
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Eng. Rate
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {insights.map((ad) => (
                <tr key={ad.id} className="hover:bg-yellow-50/50">
                  <td className="px-4 py-3 max-w-xs">
                    <p className="text-sm text-gray-900 truncate">
                      {ad.caption || "(unnamed)"}
                    </p>
                    <p className="text-xs text-gray-400">
                      {ad.created_time
                        ? new Date(ad.created_time).toLocaleDateString()
                        : "—"}
                    </p>
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {ad.impressions?.toLocaleString() ?? "—"}
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {ad.swipes?.toLocaleString() ?? "—"}
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {ad.spend != null ? `$${ad.spend.toFixed(2)}` : "—"}
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {ad.conversions ?? "—"}
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {ad.engagement_rate != null
                      ? `${ad.engagement_rate}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && insights.length === 0 && !error && (
        <p className="text-gray-500 text-sm">
          No Snapchat ad data found for this account.
        </p>
      )}
    </div>
  );
}
