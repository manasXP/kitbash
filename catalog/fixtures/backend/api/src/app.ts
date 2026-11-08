import Fastify from "fastify";
import { recipeRoutes } from "./routes/recipes.js";

/** App factory: build the instance without listening, so tests can inject requests. */
export function buildApp() {
  const app = Fastify({ logger: false });
  app.get("/health", async () => ({ status: "ok" }));
  app.register(recipeRoutes);
  return app;
}
