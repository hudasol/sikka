import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes, makeQueryClient } from "./App";
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
    expect(screen.getByTestId("figure-ranked")).toHaveTextContent("Partial data");
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
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
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
    await user.click(screen.getByRole("button", { name: "تبديل المظهر الداكن" }));
    expect(["dark", "light"]).toContain(document.documentElement.dataset.theme);
  });
});
