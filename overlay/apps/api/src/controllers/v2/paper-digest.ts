import type { NextFunction, Request, Response } from "express";
import multer from "multer";

const MAX_FILES = 20;
const MAX_FILE_BYTES = 100 * 1024 * 1024;
const MAX_BUNDLE_BYTES = 500 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 5 * 60 * 1000;
const DEFAULT_SERVICE_URL = "http://paper-digest:8088/v1/digest";

const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    files: MAX_FILES,
    fileSize: MAX_FILE_BYTES,
    fields: 8,
    fieldSize: 1024 * 1024,
  },
});

const uploadFields = upload.fields([
  { name: "files", maxCount: MAX_FILES },
  { name: "file", maxCount: 1 },
]);

export function paperDigestUploadMiddleware(
  req: Request,
  res: Response,
  next: NextFunction,
): void {
  uploadFields(req, res, error => {
    if (error instanceof multer.MulterError) {
      const status = error.code === "LIMIT_FILE_SIZE" ? 413 : 400;
      res.status(status).json({
        success: false,
        status: "NOT_SOURCE_READY",
        error: `Invalid paper-digest upload: ${error.message}`,
      });
      return;
    }
    if (error) {
      next(error);
      return;
    }
    next();
  });
}

type FileMap = Record<string, Express.Multer.File[]>;

function requestFiles(req: Request): Express.Multer.File[] {
  const value = req.files;
  if (!value) return [];
  if (Array.isArray(value)) return value;
  const mapped = value as FileMap;
  return [...(mapped.files ?? []), ...(mapped.file ?? [])];
}

function positiveInteger(raw: string | undefined, fallback: number): number {
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? Math.trunc(parsed) : fallback;
}

export async function paperDigestController(
  req: Request,
  res: Response,
): Promise<void> {
  const files = requestFiles(req);
  if (files.length === 0) {
    res.status(400).json({
      success: false,
      status: "NOT_SOURCE_READY",
      error: "At least one file is required. Upload the full paper PDF under files or file.",
    });
    return;
  }
  if (files.length > MAX_FILES) {
    res.status(400).json({
      success: false,
      status: "NOT_SOURCE_READY",
      error: `At most ${MAX_FILES} files are accepted in one evidence bundle.`,
    });
    return;
  }
  const bundleBytes = files.reduce((total, file) => total + file.size, 0);
  if (bundleBytes > MAX_BUNDLE_BYTES) {
    res.status(413).json({
      success: false,
      status: "NOT_SOURCE_READY",
      error: "The evidence bundle exceeds 500 MB.",
    });
    return;
  }

  const serviceUrl = new URL(process.env.PAPER_DIGEST_SERVICE_URL ?? DEFAULT_SERVICE_URL);
  const rawRequested = req.query.raw === "1" || req.query.raw === "true" || req.accepts(["text/markdown"]) === "text/markdown";
  if (rawRequested) serviceUrl.searchParams.set("raw", "true");
  const timeoutMs = positiveInteger(
    process.env.PAPER_DIGEST_TIMEOUT_MS,
    DEFAULT_TIMEOUT_MS,
  );
  const form = new FormData();
  for (const file of files) {
    form.append(
      "files",
      new Blob([file.buffer], { type: file.mimetype || "application/octet-stream" }),
      file.originalname,
    );
  }

  const options = typeof req.body?.options === "string" ? req.body.options : undefined;
  if (options) form.append("options", options);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const upstream = await fetch(serviceUrl, {
      method: "POST",
      body: form,
      signal: controller.signal,
      headers: {
        "X-Firecrawl-Integration": "wikillm-paper-digest-v1.3.1",
      },
    });
    const body = await upstream.text();
    const contentType = upstream.headers.get("content-type") ?? "application/json; charset=utf-8";
    const digestStatus = upstream.headers.get("x-paper-digest-status") ??
      (upstream.ok ? "SOURCE_READY" : "NOT_SOURCE_READY");

    res.status(upstream.status);
    res.setHeader("Content-Type", contentType);
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) res.setHeader("Content-Disposition", disposition);
    res.setHeader("X-Paper-Digest-LLM", "false");
    res.setHeader("X-Paper-Digest-Status", digestStatus);
    res.setHeader("Cache-Control", "no-store");
    res.send(body);
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "AbortError";
    res.status(timedOut ? 504 : 502).json({
      success: false,
      status: "NOT_SOURCE_READY",
      error: timedOut
        ? `The deterministic paper-digest service exceeded ${timeoutMs} ms.`
        : "The deterministic paper-digest service is unavailable.",
    });
  } finally {
    clearTimeout(timeout);
  }
}
