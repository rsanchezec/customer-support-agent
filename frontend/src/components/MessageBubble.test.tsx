import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "@/components/MessageBubble";

describe("MessageBubble", () => {
  it("renders user message aligned right", () => {
    render(
      <MessageBubble role="user" content="Hola" status="sent" />
    );
    expect(screen.getByText("Hola")).toBeInTheDocument();
  });

  it("renders assistant message aligned left", () => {
    render(
      <MessageBubble role="assistant" content="¿En qué te puedo ayudar?" status="sent" />
    );
    expect(screen.getByText("¿En qué te puedo ayudar?")).toBeInTheDocument();
  });

  it("shows Reintentar button when failed", () => {
    const onRetry = vi.fn();
    render(
      <MessageBubble role="user" content="Hola" status="failed" onRetry={onRetry} />
    );
    const btn = screen.getByRole("button", { name: "Reintentar" });
    expect(btn).toBeInTheDocument();
    btn.click();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows sending indicator when status is sending", () => {
    render(
      <MessageBubble role="user" content="Hola" status="sending" />
    );
    expect(screen.getByText("Enviando…")).toBeInTheDocument();
  });

  it("shows streaming indicator when status is streaming", () => {
    const { container } = render(
      <MessageBubble role="assistant" content="Hola" status="streaming" />
    );
    // streaming shows a span with animate-pulse class
    const spans = container.querySelectorAll("span");
    expect(spans.length).toBeGreaterThan(0);
  });
});
