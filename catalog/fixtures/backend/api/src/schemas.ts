import { z } from "zod";

export const StageInput = z.object({
  name: z.string().min(1),
  targetC: z.number().min(20).max(250),
  seconds: z.number().int().positive(),
});

export const RecipeInput = z.object({
  name: z.string().min(1),
  servings: z.number().int().min(1).max(8),
  stages: z.array(StageInput).min(1),
});

export type RecipeInput = z.infer<typeof RecipeInput>;

export type Recipe = RecipeInput & { id: string; createdAt: string };
