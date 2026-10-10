import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadApiConfig, request, saveApiConfig } from "./client";

describe("API client", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("refreshes an expired access token and retries the request", async () => {
    saveApiConfig({
      baseUrl: "https://example.test",
      accessToken: "expired",
      refreshToken: "refresh-token",
    });
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "renewed" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "pong" }), { status: 200 }));

    await expect(request<{ status: string }>("/ping")).resolves.toEqual({ status: "pong" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toBe("https://example.test/api/v1/token/refresh");
    expect(loadApiConfig().accessToken).toBe("renewed");
  });

  it("clears an invalid session when token refresh fails", async () => {
    saveApiConfig({
      baseUrl: "https://example.test",
      accessToken: "expired",
      refreshToken: "invalid-refresh-token",
    });
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 }));

    await expect(request("/ping")).rejects.toMatchObject({ status: 401, endpoint: "/token/refresh" });
    expect(loadApiConfig()).toEqual({ baseUrl: "", accessToken: "", refreshToken: "" });
  });
});
