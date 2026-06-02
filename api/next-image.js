const fs = require("fs");
const path = require("path");

const ALLOWED_PREFIXES = ["_next/static/media/", "project/"];

const MIME_TYPES = {
  ".avif": "image/avif",
  ".webp": "image/webp",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
};

function resolveImagePath(rawUrl) {
  const decoded = decodeURIComponent(String(rawUrl)).replace(/^\/+/, "");
  if (!ALLOWED_PREFIXES.some((prefix) => decoded.startsWith(prefix))) {
    return null;
  }
  if (decoded.includes("..")) {
    return null;
  }

  const filePath = path.join(process.cwd(), decoded);
  const resolved = path.resolve(filePath);
  const root = path.resolve(process.cwd());

  if (!resolved.startsWith(root)) {
    return null;
  }

  return fs.existsSync(resolved) ? resolved : null;
}

module.exports = (req, res) => {
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.status(405).end();
    return;
  }

  const imagePath = req.query.url;
  if (!imagePath || Array.isArray(imagePath)) {
    res.status(400).end();
    return;
  }

  const resolved = resolveImagePath(imagePath);
  if (!resolved) {
    res.status(404).end();
    return;
  }

  const ext = path.extname(resolved).toLowerCase();
  const contentType = MIME_TYPES[ext] || "application/octet-stream";

  res.setHeader("Content-Type", contentType);
  res.setHeader("Cache-Control", "public, max-age=86400");

  if (req.method === "HEAD") {
    res.status(200).end();
    return;
  }

  res.status(200).send(fs.readFileSync(resolved));
};
