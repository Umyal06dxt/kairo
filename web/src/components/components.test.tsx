import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Dock } from "./Dock";
import { IconButton } from "./IconButton";
import { Orb } from "./Orb";
import { Pill } from "./Pill";
import { ScreenHeader } from "./ScreenHeader";
import { Sheet } from "./Sheet";
import { Waveform, barHeights } from "./Waveform";

describe("design-system components", () => {
  it("icon buttons are always named and forward clicks", async () => {
    const onClick = vi.fn();
    render(<IconButton icon="close" label="Cancel" onClick={onClick} />);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("pills expose their pressed state", () => {
    render(<Pill active>Fees</Pill>);
    expect(screen.getByRole("button", { name: "Fees" })).toHaveAttribute("aria-pressed", "true");
  });

  it("the dock puts the microphone in the middle and routes the other items", async () => {
    const onMic = vi.fn(), onSettings = vi.fn();
    render(<MemoryRouter initialEntries={["/chat"]}><Dock onMic={onMic} onSettings={onSettings} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Conversation" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Home" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Experiments" })).toHaveAttribute("href", "/experiments");
    expect(screen.getByRole("link", { name: "Memory board" })).toHaveAttribute("href", "/lab");
    await userEvent.click(screen.getByRole("button", { name: "Start talking" }));
    await userEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(onMic).toHaveBeenCalledOnce();
    expect(onSettings).toHaveBeenCalledOnce();
  });

  it("the header shows back and menu only when handlers are given", () => {
    const { rerender } = render(<ScreenHeader title="Voice to text" subtitle="Listening…" />);
    expect(screen.queryByRole("button", { name: "Back" })).toBeNull();
    rerender(<ScreenHeader title="Voice to text" onBack={() => {}} onMenu={() => {}} />);
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Menu" })).toBeInTheDocument();
  });

  it("the sheet renders its content only while open and closes on the close button", async () => {
    const onClose = vi.fn();
    const { rerender } = render(<Sheet open={false} title="Settings" onClose={onClose}><p>body</p></Sheet>);
    expect(screen.queryByText("body")).toBeNull();
    rerender(<Sheet open title="Settings" onClose={onClose}><p>body</p></Sheet>);
    expect(screen.getByText("body")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("the orb renders without a canvas context (jsdom) instead of crashing", () => {
    render(<Orb level={0.5} size={120} />);
    expect(screen.getByTestId("orb")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Voice activity" })).toBeInTheDocument();
  });

  it("the waveform is deterministic and marks played bars", () => {
    expect(barHeights(10, 3)).toEqual(barHeights(10, 3));
    expect(barHeights(10, 3)).not.toEqual(barHeights(10, 4));
    const { container } = render(<Waveform bars={10} progress={0.5} />);
    expect(container.querySelectorAll("i")).toHaveLength(10);
    expect(container.querySelectorAll(".done")).toHaveLength(5);
  });
});
