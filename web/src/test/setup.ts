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
      try {
        const body = readFileSync(resolve(SNAPSHOT, `.${clean.split("?")[0]}.json`), "utf-8");
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
