import * as cheerio from "cheerio";

function participantId(sender, instance) {
  return instance ? `${sender} ${instance}` : sender;
}

export function validateSharedNetUrl(input) {
  let url;
  try {
    url = new URL(input);
  } catch {
    throw new Error("Enter a valid SharedNet conversation URL.");
  }

  const allowedHosts = new Set(["sharednet.ai", "www.sharednet.ai"]);
  if (url.protocol !== "https:" || !allowedHosts.has(url.hostname)) {
    throw new Error("Only HTTPS links from sharednet.ai are supported.");
  }
  if (!/^\/s\/[A-Za-z0-9_-]+\/?$/.test(url.pathname)) {
    throw new Error("Enter a SharedNet public conversation link (/s/...).");
  }
  url.hash = "";
  return url;
}

export function parseSharedNetHtml(html, sourceUrl = null) {
  const $ = cheerio.load(html);
  const messages = $("article.room-message").map((fallbackIndex, element) => {
    const article = $(element);
    const content = article.find(".room-message-content").first();
    const sender = article.find(".room-message-sender").first().text().trim() || "Unknown agent";
    const instance = article.find(".room-message-instance").first().text().trim().replace(/^·/, "");
    const label = article.attr("aria-label") || "";
    const explicitIndex = Number(label.match(/\d+/)?.[0]);

    return {
      index: Number.isFinite(explicitIndex) ? explicitIndex : fallbackIndex + 1,
      participantId: participantId(sender, instance),
      sender,
      instance,
      runtime: article.attr("data-runtime-kind") || "unknown",
      timestamp: article.find("time").first().attr("datetime") || null,
      text: content.text().replace(/\s+/g, " ").trim(),
      links: content.find("a[href]").length,
      codeBlocks: content.find("pre, code").length
    };
  }).get();

  if (!messages.length) {
    throw new Error("No SharedNet messages were found on this page.");
  }

  return {
    source: {
      provider: "sharednet",
      url: sourceUrl
    },
    title: $("h1").first().text().trim()
      || $("title").text().replace(/\s+[—-]\s+SharedNet$/, "").trim()
      || "Untitled conversation",
    description: $('meta[name="description"]').attr("content") || null,
    messages
  };
}
