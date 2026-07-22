import { describe, expect, it } from "vitest";

import { developmentApiProxy } from "../dev-api-proxy";

describe("development API proxy", () => {
  it("keeps relative API requests inside the Compose network", () => {
    expect(developmentApiProxy()["/api"]).toMatchObject({
      changeOrigin: true,
      target: "http://backend:8000",
    });
  });

  it("allows an explicit development backend target", () => {
    expect(developmentApiProxy("http://127.0.0.1:8000")["/api"].target).toBe(
      "http://127.0.0.1:8000"
    );
  });
});
