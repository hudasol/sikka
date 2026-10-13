import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes, makeQueryClient } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { SCREENS } from "./components/Layout";
import i18n from "./i18n";
import { SettingsProvider } from "./lib/settings";
import { installSnapshotFetch } from "./test/setup";

vi.mock("./components/MapView", () => ({
  default: ({ label }: { label: string }) => <div role="region" aria-label={label} />,
}));

function renderAt(path: string, client: QueryClient = makeQueryClient()) {
  return render(
    <QueryClientProvider client={client}>
      <SettingsProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </SettingsProvider>
    </QueryClientProvider>,
  );
}

beforeEach(async () => {
  installSnapshotFetch();
  await i18n.changeLanguage("en");
  document.documentElement.lang = "en";
  document.documentElement.dir = "ltr";
});

describe("every screen", () => {
  for (const s of SCREENS) {
    it(`shows the synthetic data banner on ${s.path}`, () => {
      renderAt(s.path);
      const banner = screen.getByTestId("synthetic-banner");
      expect(banner).toHaveTextContent(
        "Synthetic data. No real crash, traffic or road records are used.",
      );
      expect(within(banner).queryByRole("button")).toBeNull();
    });
  }
});

describe("overview", () => {
  it("shows headline figures and the producer by family matrix", async () => {
    renderAt("/");
    const matrix = await screen.findByTestId("conformance-matrix");
    for (const p of ["PRODUCER_A", "PRODUCER_B", "PRODUCER_C", "PRODUCER_D"]) {
      expect(within(matrix).getByText(p)).toBeInTheDocument();
    }
    expect(screen.getByTestId("figure-producers")).toHaveTextContent("of 4");
    expect(await screen.findByTestId("top10")).toBeInTheDocument();
    expect(screen.getByTestId("figure-ranked")).toHaveTextContent("of 240");
    expect(screen.getAllByRole("img", { name: /share of records passing/i }).length).toBe(1);
  });

  it("shows an error state when the API fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 500 })),
    );
    const client = makeQueryClient();
    client.setDefaultOptions({ queries: { retry: false } });
    renderAt("/", client);
    const alerts = await screen.findAllByRole("alert");
    expect(alerts[0]).toHaveTextContent("could not be loaded");
  });
});

describe("validate", () => {
  it("validates a sample and groups results by family", async () => {
    const user = userEvent.setup();
    renderAt("/validate");
    const select = await screen.findByLabelText("Sample feed");
    await user.selectOptions(select, "broken/crash_records_producer_b.ndjson");
    await user.click(screen.getByRole("button", { name: "Validate sample" }));
    const report = await screen.findByTestId("report", {}, { timeout: 5000 });
    expect(within(report).getByText(/Structural \(S\)/)).toBeInTheDocument();
    expect(within(report).getByText(/Privacy \(P\)/)).toBeInTheDocument();
    expect(within(report).getAllByText("SK-S008").length).toBeGreaterThan(0);
    expect(within(report).getByRole("link", { name: "Download JSON report" })).toBeInTheDocument();
    expect(report).not.toHaveTextContent("Synthetic Person");
  });
});

describe("language and settings", () => {
  it("switches to Arabic, right to left, with Arabic Indic digits on request", async () => {
    const user = userEvent.setup();
    renderAt("/");
    await user.click(screen.getByRole("button", { name: "Switch the interface to Arabic" }));
    await waitFor(() => expect(document.documentElement.dir).toBe("rtl"));
    expect(screen.getByTestId("synthetic-banner")).toHaveTextContent("بيانات مصطنعة");
    await user.click(screen.getByRole("button", { name: "تبديل الأرقام الهندية" }));
    const figure = await screen.findByTestId("figure-producers");
    expect(figure.textContent ?? "").toMatch(/[٠-٩]/);
    const before = document.documentElement.dataset.theme;
    await user.click(screen.getByRole("button", { name: "تبديل المظهر الداكن" }));
    await waitFor(() =>
      expect(document.documentElement.dataset.theme).toBe(before === "dark" ? "light" : "dark"),
    );
  });

  it("shows Arabic rule titles and keeps English rule text marked as English", async () => {
    const user = userEvent.setup();
    renderAt("/contract");
    await user.click(screen.getByRole("button", { name: "Switch the interface to Arabic" }));
    const rule = await screen.findByText("SK-P002", {}, { timeout: 5000 });
    const details = rule.closest("details")!;
    const summary = details.querySelector("summary")!;
    const title = (summary.textContent ?? "").split("SK-P002")[1] ?? "";
    expect(title.trim().slice(0, 8)).toMatch(/[\u0600-\u06FF]/);
    const english = details.querySelectorAll('[lang="en"][dir="ltr"]');
    expect(english.length).toBeGreaterThanOrEqual(3);
  });
});

describe("robustness", () => {
  it("shows a not found screen for an unknown address", async () => {
    renderAt("/no-such-screen");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Page not found");
    expect(screen.getByTestId("synthetic-banner")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the overview" })).toBeInTheDocument();
  });

  it("keeps the layout when a screen throws", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    function Broken(): never {
      throw new Error("broken view");
    }
    render(
      <ErrorBoundary fallback={(e) => <p role="alert">{e.message}</p>}>
        <Broken />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("broken view");
    warn.mockRestore();
    error.mockRestore();
  });
});

describe("full screens", () => {
  it("ranks blackspots with intervals and explains a rank", { timeout: 20_000 }, async () => {
    const user = userEvent.setup();
    renderAt("/blackspots");
    const table = await screen.findByTestId("ranking-table", {}, { timeout: 5000 });
    const buttons = within(table).getAllByRole("button", { name: /^SEG-/ });
    expect(buttons.length).toBeGreaterThan(10);
    expect(within(table).getAllByRole("img", { name: /90 percent interval/ }).length).toBe(
      buttons.length,
    );
    await user.click(buttons[0]!);
    expect(await screen.findByTestId("why", {}, { timeout: 5000 })).toHaveTextContent(
      "crashes per year",
    );
    expect(screen.getByText(/Segments not ranked/)).toBeInTheDocument();
  });

  it("shows the bilingual field dictionary and the version diff", async () => {
    renderAt("/contract");
    const dict = await screen.findByTestId("field-dictionary");
    expect(within(dict).getByText("occurred_at")).toBeInTheDocument();
    expect(await screen.findByTestId("contract-diff")).toHaveTextContent("work_zone");
  });

  it("shows producer scorecards and the fault catalogue", async () => {
    renderAt("/conformance");
    expect(await screen.findByTestId("scorecard-PRODUCER_B")).toBeInTheDocument();
    expect(await screen.findByTestId("fault-catalogue")).toHaveTextContent("F25");
  });

  it("searches lineage and shows the chain", { timeout: 20_000 }, async () => {
    const user = userEvent.setup();
    renderAt("/lineage");
    await user.type(screen.getByLabelText("Canonical or source id"), "PB-0000007");
    await user.click(screen.getByRole("button", { name: "Search" }));
    const results = await screen.findByTestId("lineage-results");
    const first = await within(results).findAllByRole("button");
    await user.click(first[0]!);
    expect(await screen.findByTestId("lineage-entry", {}, { timeout: 5000 })).toHaveTextContent(
      "PRODUCER_B",
    );
  });

  it("renders preregistered predictions with verdicts and limitations", async () => {
    renderAt("/method");
    expect(await screen.findByTestId("limitations")).toHaveTextContent("synthetic world only");
    expect(await screen.findByTestId("predictions")).toHaveTextContent("P1.1");
  });

  it("plans missions with the simulation disclaimer", async () => {
    renderAt("/tasking");
    expect(screen.getByTestId("tasking-disclaimer")).toHaveTextContent(
      "simulation and review only",
    );
    expect(await screen.findByTestId("missions")).toHaveTextContent("M01");
    expect(await screen.findByTestId("tasking-comparison")).toHaveTextContent("Random");
  });

  it("frames the pilot path as a proposal", () => {
    renderAt("/pilot");
    expect(screen.getByText(/Proposal only/)).toBeInTheDocument();
  });
});

describe("locales", () => {
  it("have the same keys in English and Arabic", async () => {
    const en = (await import("./locales/en.json")).default as Record<string, unknown>;
    const ar = (await import("./locales/ar.json")).default as Record<string, unknown>;
    const keys = (o: Record<string, unknown>, p = ""): string[] =>
      Object.entries(o).flatMap(([k, v]) =>
        v && typeof v === "object" ? keys(v as Record<string, unknown>, `${p}${k}.`) : [`${p}${k}`],
      );
    expect(keys(ar).sort()).toEqual(keys(en).sort());
  });
});
