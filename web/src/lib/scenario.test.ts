import { scenarioLabel, shortDomain } from "./scenario";

describe("scenario helpers", () => {
  it("drops the ordering code from scenario names", () => {
    expect(scenarioLabel("B1 Lost debit card")).toBe("Lost debit card");
    expect(scenarioLabel("S10 Mixed rapid-fire")).toBe("Mixed rapid-fire");
    expect(scenarioLabel("Plain name")).toBe("Plain name");
  });
  it("shortens a domain title to the descriptive part", () => {
    expect(shortDomain("Harbor FCU - credit union voice support")).toBe("Credit union voice support");
    expect(shortDomain("NovaCRM")).toBe("NovaCRM");
  });
});
