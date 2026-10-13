import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { SettingsProvider } from "./lib/settings";
import { Blackspots } from "./pages/Blackspots";
import { Conformance } from "./pages/Conformance";
import { Contract } from "./pages/Contract";
import { Lineage } from "./pages/Lineage";
import { Method } from "./pages/Method";
import { Overview } from "./pages/Overview";
import { Pilot } from "./pages/Pilot";
import { Tasking } from "./pages/Tasking";
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
        <Route path="contract" element={<Contract />} />
        <Route path="conformance" element={<Conformance />} />
        <Route path="blackspots" element={<Blackspots />} />
        <Route path="lineage" element={<Lineage />} />
        <Route path="tasking" element={<Tasking />} />
        <Route path="method" element={<Method />} />
        <Route path="pilot" element={<Pilot />} />
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
