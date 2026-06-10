import { useState } from "react";

/**
 * SnapchatShareButton – Creative Kit web sharing.
 *
 * Since Snapchat does NOT allow server-to-server organic story posting,
 * this component uses the Snapchat Creative Kit / Web Share deep-link
 * to open the Snapchat app on the user's mobile device so they can
 * finish publishing the story themselves.
 *
 * Usage:
 *   <SnapchatShareButton
 *     mediaUrl="https://example.com/image.jpg"
 *     attachmentUrl="https://example.com/landing"
 *     caption="Check this out!"
 *   />
 */

// Snapchat deep link / Creative Kit Web URL builder
function buildSnapShareUrl(mediaUrl, attachmentUrl, caption, stickerUrl) {
  // Snap Creative Kit uses a URL scheme to launch the Snapchat camera
  // with pre-loaded content for the user to share.
  // On mobile web, snapchat://creative opens the app.
  // The web fallback is https://www.snapchat.com/scan

  const params = new URLSearchParams();

  if (attachmentUrl) {
    params.set("attachmentUrl", attachmentUrl);
  }

  // For web-based sharing, Snapchat provides the Snap Kit Web SDK,
  // but the simplest cross-platform approach is the share URL:
  const shareBase = "https://www.snapchat.com/scan";
  return `${shareBase}?${params.toString()}`;
}

export default function SnapchatShareButton({
  mediaUrl,
  attachmentUrl,
  caption,
  stickerUrl,
}) {
  const [shared, setShared] = useState(false);

  function handleShare() {
    // Try native Web Share API first (works on mobile browsers)
    if (navigator.share) {
      navigator
        .share({
          title: caption || "Check this out on Snapchat!",
          text: caption || "",
          url: attachmentUrl || mediaUrl,
        })
        .then(() => setShared(true))
        .catch(() => {
          // User cancelled or error – fall through to deep link
          openSnapDeepLink();
        });
    } else {
      openSnapDeepLink();
    }
  }

  function openSnapDeepLink() {
    const url = buildSnapShareUrl(mediaUrl, attachmentUrl, caption, stickerUrl);
    window.open(url, "_blank", "noopener,noreferrer");
    setShared(true);
  }

  return (
    <button
      onClick={handleShare}
      className="inline-flex items-center gap-2 px-4 py-2 bg-yellow-400 text-gray-900 text-sm font-semibold rounded-lg hover:bg-yellow-500 transition shadow"
    >
      {/* Snapchat ghost icon (inline SVG) */}
      <svg
        className="w-5 h-5"
        viewBox="0 0 24 24"
        fill="currentColor"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d="M12.166 2C14.236 2 15.82 2.878 16.858 4.606c.578.96.78 2.06.78 3.16 0 .44-.026.87-.066 1.3.22.1.46.15.72.15.34 0 .62-.1.86-.26.14-.1.32-.16.5-.16.46 0 .86.38.86.86 0 .38-.26.72-.64.86-.18.06-.36.12-.56.18-.58.18-1.3.4-1.52.86-.06.12-.08.24-.06.38.24 1.38.88 2.64 1.88 3.66.18.18.38.34.58.48.42.28.58.56.58.82 0 .54-.7.9-1.38 1.12-.28.1-.58.18-.88.22-.18.02-.3.08-.4.22-.12.16-.26.44-.56.72-.32.3-.74.44-1.18.44-.3 0-.6-.06-.94-.14-.56-.14-1.14-.28-1.94-.28-.82 0-1.4.14-1.96.28-.34.08-.64.14-.94.14-.44 0-.86-.14-1.18-.44-.3-.28-.44-.56-.56-.72-.1-.14-.22-.2-.4-.22-.3-.04-.6-.12-.88-.22-.68-.22-1.38-.58-1.38-1.12 0-.26.16-.54.58-.82.2-.14.4-.3.58-.48 1-1.02 1.64-2.28 1.88-3.66.02-.14 0-.26-.06-.38-.22-.46-.94-.68-1.52-.86-.2-.06-.38-.12-.56-.18-.38-.14-.64-.48-.64-.86 0-.48.4-.86.86-.86.18 0 .36.06.5.16.24.16.52.26.86.26.26 0 .5-.06.72-.16-.04-.42-.066-.86-.066-1.3 0-1.1.2-2.2.78-3.16C8.346 2.878 9.93 2 12 2h.166z" />
      </svg>
      {shared ? "Shared!" : "Share to Snapchat"}
    </button>
  );
}
