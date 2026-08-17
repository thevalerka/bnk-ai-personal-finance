import { describe, expect, it } from "vitest";
import { fromSmallestUnit, toSmallestUnit } from "../solanaWallet";

describe("toSmallestUnit", () => {
  it("converts a whole-number amount", () => {
    expect(toSmallestUnit("10", 6)).toBe("10000000");
  });

  it("converts a fractional amount without floating-point drift", () => {
    expect(toSmallestUnit("12.5", 6)).toBe("12500000");
  });

  it("truncates extra fractional digits beyond the token's decimals", () => {
    expect(toSmallestUnit("1.123456789", 6)).toBe("1123456");
  });

  it("handles a large whole-number amount exactly", () => {
    expect(toSmallestUnit("123456789", 6)).toBe("123456789000000");
  });
});

describe("fromSmallestUnit", () => {
  it("is the inverse of toSmallestUnit for a whole amount", () => {
    expect(fromSmallestUnit("10000000", 6)).toBe("10");
  });

  it("is the inverse of toSmallestUnit for a fractional amount", () => {
    expect(fromSmallestUnit("12500000", 6)).toBe("12.5");
  });

  it("handles amounts smaller than one whole unit", () => {
    expect(fromSmallestUnit("500000", 6)).toBe("0.5");
  });
});
