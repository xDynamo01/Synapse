import { describe, expect, it } from "vitest";
import { createPresencePublicationGate } from "../src/renderer/presencePublication";

describe("audio visual publication budget", () => {
  it("limits 60Hz amplitude updates without delaying phase transitions", () => {
    const publish = createPresencePublicationGate();
    let updates = 0;
    for (let frame = 0; frame < 60; frame += 1) {
      if (publish("listening", frame / 60, frame * 1000 / 60)) updates += 1;
    }
    expect(updates).toBeLessThanOrEqual(13);
    expect(publish("speaking", 0.2, 990)).toBe(true);
    expect(publish("cooldown", 0, 991)).toBe(true);
  });
  it("does not rerender unchanged silence", () => {
    const publish = createPresencePublicationGate();
    expect(publish("listening", 0, 0)).toBe(true);
    expect(publish("listening", 0, 1000)).toBe(false);
    expect(publish("listening", 0.3, 1001)).toBe(true);
  });
});
