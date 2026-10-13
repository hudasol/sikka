import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { SettingsProvider } from "./lib/settings";
import { Overview } from "./pages/Overview";
import { Placeholder } from "./pages/Placeholder";
import { Validate } from "./pages/Validate";

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: 1, refetchOnWindowFocus: false } },
  });
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="validate" element={<Validate />} />
        <Route path="contract" element={<Placeholder screen="contract" />} />
        <Route path="conformance" element={<Placeholder screen="conformance" />} />
        <Route path="blackspots" element={<Placeholder screen="blackspots" />} />
        <Route path="lineage" element={<Placeholder screen="lineage" />} />
        <Route path="tasking" element={<Placeholder screen="tasking" />} />
        <Route path="method" element={<Placeholder screen="method" />} />
        <Route path="pilot" element={<Placeholder screen="pilot" />} />
        <Route path="*" element={<Placeholder screen="overview" />} />
      </Route>
    </Routes>
  );
}

export function App({ client = makeQueryClient() }: { client?: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <SettingsProvider>
        <HashRouter>
          <AppRoutes />
        </HashRouter>
      </SettingsProvider>
    </QueryClientProvider>
  );
}
