import {
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import {
  clearQueryFailure,
  reportQueryFailure,
} from "./components/ErrorBanner";
import { describeError } from "./errors";
import "./styles.css";

// §6 Errors: a failed *query* means the app could not load something — that is
// the global dismissible banner. Wiring it into the query cache means no screen
// has to remember to report one, and it clears itself as soon as any query
// succeeds again. Mutation failures stay inline (plus a toast) next to the
// control that triggered them, never here.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
  queryCache: new QueryCache({
    onError: (error) => reportQueryFailure(describeError(error)),
    onSuccess: () => clearQueryFailure(),
  }),
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
