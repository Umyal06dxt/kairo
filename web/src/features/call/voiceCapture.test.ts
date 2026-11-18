import { blobToBase64, pickMimeType, splitInterim } from "./voiceCapture";

describe("voice capture helpers", () => {
  it("picks the first supported recording format, or lets the browser choose", () => {
    expect(pickMimeType((t) => t.startsWith("audio/ogg"))).toBe("audio/ogg;codecs=opus");
    expect(pickMimeType(() => true)).toBe("audio/webm;codecs=opus");
    expect(pickMimeType(() => false)).toBeUndefined();
  });
  it("splits live speech into settled words and the latest few", () => {
    expect(splitInterim("how much is the overdraft fee on a checking account")).toEqual({
      done: "how much is the overdraft", live: "fee on a checking account",
    });
    expect(splitInterim("hello there")).toEqual({ done: "", live: "hello there" });
    expect(splitInterim("   ")).toEqual({ done: "", live: "" });
  });
  it("encodes a blob as bare base64 (no data: prefix)", async () => {
    expect(await blobToBase64(new Blob(["hi"], { type: "text/plain" }))).toBe("aGk=");
  });
});
