import "@testing-library/jest-dom/vitest";
import "../i18n";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    value: (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
  });
}

const SNAPSHOT = resolve(__dirname, "../../public/snapshot");

// Serve API calls from the committed static snapshot so tests see real responses.
export function installSnapshotFetch(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const path = url
        .replace(/^https?:\/\/[^/]+/, "")
        .replace(/^\.?\/?snapshot/, "")
        .replace(/\.json$/, "");
      const clean = path.startsWith("/") ? path : `/${path}`;
      if (init?.method === "POST" && clean === "/v1/validate") {
        const form = init.body as FormData;
        const samples = JSON.parse(readFileSync(resolve(SNAPSHOT, "v1/samples.json"), "utf-8")) as {
          name: string;
          report_id: string;
        }[];
        const hit = samples.find((s) => s.name === form.get("sample"));
        return new Response(JSON.stringify({ report_id: hit?.report_id, notice: "" }), {
          status: 201,
        });
      }
      const [route = clean, query = ""] = clean.split("?");
      const detail = /^\/v1\/lineage\/(.+)$/.exec(route);
      if (detail) {
        const id = decodeURIComponent(detail[1]!);
        const key = id.startsWith("CC-") ? id.slice(0, 5) : id.slice(0, 2);
        const bucket = JSON.parse(
          readFileSync(resolve(SNAPSHOT, `v1/lineage-buckets/${key}.json`), "utf-8"),
        ) as Record<string, unknown>;
        return new Response(JSON.stringify(bucket[id]), { status: bucket[id] ? 200 : 404 });
      }
      if (route === "/v1/lineage" && query) {
        const q = (new URLSearchParams(query).get("q") ?? "").toUpperCase();
        const index = JSON.parse(readFileSync(resolve(SNAPSHOT, "v1/lineage.json"), "utf-8")) as {
          items: { canonical_id: string; record_ids: string[] }[];
        };
        const items = index.items
          .filter(
            (i) => !q || i.canonical_id.includes(q) || i.record_ids.some((r) => r.includes(q)),
          )
          .slice(0, 50);
        return new Response(JSON.stringify({ items }), { status: 200 });
      }
      try {
        const body = readFileSync(resolve(SNAPSHOT, `.${route}.json`), "utf-8");
        return new Response(body, { status: 200, headers: { "content-type": "application/json" } });
      } catch {
        return new Response(
          JSON.stringify({
            type: "about:blank",
            title: "Not found",
            status: 404,
            detail: "missing",
            instance: clean,
          }),
          { status: 404, headers: { "content-type": "application/problem+json" } },
        );
      }
    }),
  );
}
