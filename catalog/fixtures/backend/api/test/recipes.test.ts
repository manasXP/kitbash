import { beforeEach, describe, expect, it } from "vitest";
import { buildApp } from "../src/app.js";
import { store } from "../src/routes/recipes.js";

const valid = {
  name: "Dal tadka",
  servings: 2,
  stages: [
    { name: "temper", targetC: 170, seconds: 90 },
    { name: "simmer", targetC: 95, seconds: 900 },
  ],
};

describe("recipes", () => {
  beforeEach(() => store.clear());

  it("creates and returns a recipe", async () => {
    const app = buildApp();
    const created = await app.inject({ method: "POST", url: "/recipes", payload: valid });
    expect(created.statusCode).toBe(201);
    const { id } = created.json();
    const fetched = await app.inject({ method: "GET", url: `/recipes/${id}` });
    expect(fetched.statusCode).toBe(200);
    expect(fetched.json().name).toBe("Dal tadka");
  });

  it("answers 404 for an unknown id", async () => {
    const app = buildApp();
    const res = await app.inject({ method: "GET", url: "/recipes/nope" });
    expect(res.statusCode).toBe(404);
  });
});
