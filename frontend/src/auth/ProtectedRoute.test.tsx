import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "@/auth/ProtectedRoute";

// Use vi.hoisted to share mock references across vi.mock and tests
const { mockLoginRedirect, mockUseIsAuthenticated, mockUseMsal } = vi.hoisted(
  () => ({
    mockLoginRedirect: vi.fn(() => Promise.resolve()),
    mockUseIsAuthenticated: vi.fn(() => false),
    mockUseMsal: vi.fn(() => ({
      instance: { loginRedirect: mockLoginRedirect },
      accounts: [],
    })),
  })
);

vi.mock("@azure/msal-react", () => ({
  useIsAuthenticated: () => mockUseIsAuthenticated(),
  useMsal: () => mockUseMsal(),
}));

const TestChild = () => <div data-testid="protected">protected content</div>;

describe("ProtectedRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls loginRedirect when not authenticated", () => {
    mockUseIsAuthenticated.mockReturnValue(false);

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

    expect(mockLoginRedirect).toHaveBeenCalled();
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
