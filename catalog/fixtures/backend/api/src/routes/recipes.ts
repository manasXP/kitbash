import type { FastifyInstance } from "fastify";
import { randomUUID } from "node:crypto";
import type { Recipe, RecipeInput } from "../schemas.js";

export const store = new Map<string, Recipe>();

export async function recipeRoutes(app: FastifyInstance) {
  app.get("/recipes", async () => Array.from(store.values()));

  app.get<{ Params: { id: string } }>("/recipes/:id", async (request, reply) => {
    const recipe = store.get(request.params.id);
    if (!recipe) {
      return reply.code(404).send({ error: "not found" });
    }
    return recipe;
  });

  app.post("/recipes", async (request, reply) => {
    const input = request.body as RecipeInput;
    const totalSeconds = input.stages.reduce((sum, s) => sum + s.seconds, 0);
    const recipe: Recipe = {
      ...input,
      id: randomUUID(),
      createdAt: new Date().toISOString(),
    };
    store.set(recipe.id, recipe);
    request.log.info({ id: recipe.id, totalSeconds }, "recipe created");
    return reply.code(201).send(recipe);
  });
}
