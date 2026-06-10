import { useState, useEffect, useMemo } from "react";
import SnapchatOAuthButton from "./components/SnapchatOAuthButton";
import SnapchatDashboard from "./components/SnapchatDashboard";
import SnapchatShareButton from "./components/SnapchatShareButton";

function engagementBadge(rate) {
  if (rate === null || rate === undefined) return null;
  if (rate < 1)
    return (
      <span className="ml-2 text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">
        Needs attention
      </span>
    );
  if (rate > 5)
    return (
      <span className="ml-2 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
        High Engagement
      </span>
    );
  return null;
}

function ImagePreview({ file, idx }) {
  const [previewUrl, setPreviewUrl] = useState(null);

  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  if (!previewUrl) return null;

  return (
    <img
      src={previewUrl}
      alt={`preview-${idx}`}
      className="w-full h-full object-cover transition duration-200 group-hover:scale-105"
    />
  );
}

export default function App() {
  const [connected, setConnected] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState("");
  const [insights, setInsights] = useState([]);
  const [loading, setLoading] = useState(false);
  const [postMessage, setPostMessage] = useState("");
  const [postImages, setPostImages] = useState([]);
  const [fileInputKey, setFileInputKey] = useState(Date.now());
  const [isPosting, setIsPosting] = useState(false);
  const [postStatus, setPostStatus] = useState(null);

  const [commentsModalOpen, setCommentsModalOpen] = useState(false);
  const [currentComments, setCurrentComments] = useState([]);
  const [isLoadingComments, setIsLoadingComments] = useState(false);
  const [activePostId, setActivePostId] = useState(null);

  useEffect(() => {
    fetch("/api/status")
      .then((r) => r.json())
      .then((d) => {
        setConnected(d.connected);
        if (d.connected) loadAccounts();
      })
      .catch(() => {});
  }, []);

  // Check URL param after OAuth redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "true") {
      setConnected(true);
      loadAccounts();
      window.history.replaceState({}, "", "/");
    }
  }, []);

  function loadAccounts() {
    fetch("/api/accounts")
      .then((r) => r.json())
      .then((data) => {
        setAccounts(data);
        if (data.length > 0) setSelectedAccount(data[0].id);
      });
  }

  function loadInsights(accountId) {
    if (!accountId) return;
    setLoading(true);
    fetch(`/api/insights?account_id=${accountId}`)
      .then((r) => r.json())
      .then((data) => {
        setInsights(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => {
        setInsights([]);
        setLoading(false);
      });
  }

  function handleViewComments(postId) {
    setActivePostId(postId);
    setCurrentComments([]);
    setCommentsModalOpen(true);
    setIsLoadingComments(true);
    fetch(`/api/comments?account_id=${selectedAccount}&post_id=${postId}`)
      .then((r) => r.json())
      .then((data) => {
        setCurrentComments(Array.isArray(data) ? data : []);
        setIsLoadingComments(false);
      })
      .catch(() => {
        setCurrentComments([]);
        setIsLoadingComments(false);
      });
  }

  useEffect(() => {
    if (selectedAccount) loadInsights(selectedAccount);
  }, [selectedAccount]);

  async function handlePost(e) {
    e.preventDefault();
    if (!postMessage.trim() || !selectedAccount) return;
    
    if (isInstagram && postImages.length === 0) {
      setPostStatus({ type: "error", message: "Instagram posts require at least one image." });
      return;
    }

    setIsPosting(true);
    setPostStatus(null);
    
    try {
      const formData = new FormData();
      formData.append("account_id", selectedAccount);
      formData.append("message", postMessage);
      if (postImages && postImages.length > 0) {
        postImages.forEach((img) => {
          formData.append("images", img);
        });
      }

      const res = await fetch("/api/publish", {
        method: "POST",
        body: formData
      });
      
      const data = await res.json();
      
      if (!res.ok) {
        throw new Error(data.detail || "Failed to publish post");
      }
      
      setPostStatus({ type: "success", message: "Post published successfully!" });
      setPostMessage("");
      setPostImages([]);
      setFileInputKey(Date.now());
      
      // Reload insights to show the new post
      loadInsights(selectedAccount);
      
    } catch (err) {
      setPostStatus({ type: "error", message: err.message });
    } finally {
      setIsPosting(false);
    }
  }

  const currentAccount = accounts.find((a) => a.id === selectedAccount);
  const isInstagram = currentAccount?.type === "instagram";

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold text-gray-900">
            Meta Insights Dashboard
          </h1>
          {connected && (
            <span className="inline-flex items-center gap-1 text-sm font-medium text-green-700 bg-green-100 px-3 py-1 rounded-full">
              <svg className="w-3 h-3 fill-green-600" viewBox="0 0 8 8">
                <circle cx="4" cy="4" r="4" />
              </svg>
              Connected
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-2">
            <a
              href="/auth/login"
              className="inline-flex items-center px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition"
            >
              + Add FB/IG
            </a>
            <SnapchatOAuthButton />
          </div>
        </div>
      </div>

      {/* Account Selector */}
      {connected && accounts.length > 0 && (
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Select Account
          </label>
          <select
            value={selectedAccount}
            onChange={(e) => setSelectedAccount(e.target.value)}
            className="block w-full max-w-xs border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.type === "facebook_page" ? "FB Page" : a.type === "instagram" ? "Instagram" : "Snapchat"})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Create Post Section */}
      {!loading && connected && currentAccount && (
        <div className="mb-8 bg-white p-6 border border-gray-200 rounded-lg shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Create Post</h2>
          <form onSubmit={handlePost}>
            <textarea
              value={postMessage}
              onChange={(e) => setPostMessage(e.target.value)}
              placeholder="What's on your mind?"
              className="w-full border border-gray-300 rounded-lg p-3 text-sm focus:ring-blue-500 focus:border-blue-500 min-h-[100px] mb-3"
              disabled={isPosting}
            />
            <div className="mb-4">
              <input 
                key={fileInputKey}
                type="file" 
                accept="image/*"
                multiple
                onChange={(e) => {
                  const selected = Array.from(e.target.files);
                  setPostImages((prev) => [...prev, ...selected]);
                }}
                className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                disabled={isPosting}
              />
              {postImages.length > 0 && (
                <div className="flex flex-wrap gap-4 mt-4">
                  {postImages.map((file, idx) => {
                    return (
                      <div key={idx} className="relative w-24 h-24 rounded-lg overflow-hidden border border-gray-200 shadow-md group">
                        <ImagePreview file={file} idx={idx} />
                        <button
                          type="button"
                          onClick={() => {
                            setPostImages((prev) => prev.filter((_, i) => i !== idx));
                          }}
                          className="absolute top-1 right-1 bg-gray-900/80 text-white hover:bg-red-600 rounded-full p-1 transition shadow duration-150 flex items-center justify-center"
                          title="Remove image"
                          style={{ width: "20px", height: "20px" }}
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="flex items-center justify-between">
              <div>
                {postStatus && (
                  <span className={`text-sm ${postStatus.type === "success" ? "text-green-600" : "text-red-600"}`}>
                    {postStatus.message}
                  </span>
                )}
              </div>
              <button
                type="submit"
                disabled={isPosting || !postMessage.trim()}
                className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition"
              >
                {isPosting ? "Publishing..." : "Publish Post"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Insights Grid */}
      {loading && <p className="text-gray-500 text-sm">Loading insights...</p>}

      {!loading && insights.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white border border-gray-200 rounded-lg overflow-hidden">
            <thead className="bg-gray-100">
              <tr>
                <th className="text-left text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Post
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Impressions
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Reach
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Likes
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Comments
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Saves
                </th>
                <th className="text-right text-xs font-semibold text-gray-600 uppercase px-4 py-3">
                  Eng. Rate
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {insights.map((post) => (
                <tr key={post.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 max-w-xs">
                    <p className="text-sm text-gray-900 truncate">
                      {post.caption || "(no caption)"}
                    </p>
                    <p className="text-xs text-gray-400">
                      {new Date(post.created_time).toLocaleDateString()}
                    </p>
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {post.impressions ?? "—"}
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {post.reach ?? "—"}
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {post.likes}
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {post.comments}
                    {post.comments > 0 && (
                      <button
                        onClick={() => handleViewComments(post.id)}
                        className="ml-2 text-xs bg-blue-50 text-blue-600 px-2 py-1 rounded hover:bg-blue-100 transition"
                      >
                        View
                      </button>
                    )}
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {post.saves}
                  </td>
                  <td className="text-right px-4 py-3 text-sm text-gray-700">
                    {post.engagement_rate !== null
                      ? `${post.engagement_rate}%`
                      : "—"}
                    {engagementBadge(post.engagement_rate)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && connected && insights.length === 0 && selectedAccount && (
        <p className="text-gray-500 text-sm">
          No posts found for this account.
        </p>
      )}

      {!connected && (
        <div className="text-center py-20 text-gray-400">
          <p className="text-lg">Connect your Meta accounts to see insights</p>
        </div>
      )}

      {/* ─── Snapchat Section ───────────────────────────────────── */}
      {connected && currentAccount?.type === "snapchat" && (
        <div className="mt-8">
          <SnapchatDashboard accountId={selectedAccount} />
          <div className="mt-4">
            <h3 className="text-sm font-medium text-gray-700 mb-2">
              Share to Snapchat Story (Organic)
            </h3>
            <SnapchatShareButton
              mediaUrl=""
              attachmentUrl={window.location.origin}
              caption="Check out our latest update!"
            />
            <p className="text-xs text-gray-400 mt-1">
              Opens Snapchat app on mobile to complete the story post.
            </p>
          </div>
        </div>
      )}

      {/* Comments Modal */}
      {commentsModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-lg w-full flex flex-col max-h-[80vh]">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">Comments</h3>
              <button 
                onClick={() => setCommentsModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 transition"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
              </button>
            </div>
            <div className="p-6 overflow-y-auto flex-1">
              {isLoadingComments ? (
                <p className="text-center text-gray-500 py-4">Loading comments...</p>
              ) : currentComments.length > 0 ? (
                <div className="space-y-4">
                  {currentComments.map((comment) => (
                    <div key={comment.id} className="bg-gray-50 p-4 rounded-lg border border-gray-100 text-sm">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-semibold text-gray-900">{comment.author}</span>
                        <span className="text-xs text-gray-500">{new Date(comment.timestamp).toLocaleDateString()}</span>
                      </div>
                      <p className="text-gray-700 whitespace-pre-wrap">{comment.text}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-center text-gray-500 py-4">No comments found.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
