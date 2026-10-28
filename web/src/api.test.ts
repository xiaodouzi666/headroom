import { afterEach, expect, it, vi } from "vitest";
import { getJSON, getText, productMessage, submitRun } from "./api";

afterEach(() => vi.unstubAllGlobals());

it("requests the versioned product view for JSON while leaving file downloads unchanged", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok" })))
    .mockResolvedValueOnce(new Response("--- a/train.py\n+++ b/train.py\n"));
  vi.stubGlobal("fetch", fetcher);
  expect(await getJSON("/api/health")).toEqual({ status: "ok" });
  expect(fetcher.mock.calls[0][1].headers).toEqual({
    "X-Headroom-View": "product-v1",
  });
  expect(await getText("/api/runs/" + "a".repeat(32) + "/patch.diff")).toBe(
    "--- a/train.py\n+++ b/train.py\n",
  );
  expect(fetcher.mock.calls[1][1].headers).toBeUndefined();
});

it("uses fixed error copy instead of arbitrary server details", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "internal provider detail" }), {
          status: 503,
        }),
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  await expect(getJSON("/api/health")).rejects.toThrow(
    "The service is temporarily unavailable. Please try again later.",
  );
  await expect(
    submitRun({
      script_text: "print(1)",
      target: "fix-oom",
      budget: "0.30",
      policy: {
        allow_numerics_change: false,
        allow_model_change: false,
        allow_batch_grad_accum: true,
        max_throughput_regression_pct: 10,
      },
    }),
  ).rejects.toThrow(
    "The service is temporarily unavailable. Please try again later.",
  );
  expect(productMessage("internal provider detail")).toBe(
    "Additional details are available in the downloaded report.",
  );
  expect(productMessage("The numerical comparison did not pass.")).toBe(
    "The numerical comparison did not pass.",
  );
});
