import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "@/auth/ProtectedRoute";

// Use vi.hoisted to share mock references across vi.mock and tests
const { mockUseIsAuthenticated } = vi.hoisted(() => ({
  mockUseIsAuthenticated: vi.fn(() => false),
}));

vi.mock("@azure/msal-react", () => ({
  useIsAuthenticated: () => mockUseIsAuthenticated(),
}));

const TestChild = () => <div data-testid="protected">protected content</div>;

describe("ProtectedRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects to login when not authenticated", () => {
    mockUseIsAuthenticated.mockReturnValue(false);

    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route
            path="/chat"
            element={
              <ProtectedRoute>
                <TestChild />
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("login page")).toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    mockUseIsAuthenticated.mockReturnValue(true);

    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Routes>
          <Route
            path="/chat"
            element={
              <ProtectedRoute>
                <TestChild />
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });
});
