import { Request, Response } from "express";
import { z } from "zod";
import { authService } from "./auth.service";

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

const refreshSchema = z.object({
  refreshToken: z.string().min(1),
});

export async function loginHandler(req: Request, res: Response) {
  try {
    const { email, password } = loginSchema.parse(req.body);
    const tokens = await authService.login(email, password);
    return res.json(tokens);
  } catch (err: any) {
    if (err.name === "ZodError") {
      return res.status(400).json({ message: "Invalid input", errors: err.errors });
    }
    if (err.message === "INVALID_CREDENTIALS") {
      return res.status(401).json({ message: "Invalid credentials" });
    }
    if (err.message === "INACTIVE") {
      return res.status(403).json({ message: "User account is inactive" });
    }
    // eslint-disable-next-line no-console
    console.error("loginHandler error", err);
    return res.status(500).json({ message: "Internal server error" });
  }
}

export async function refreshHandler(req: Request, res: Response) {
  try {
    const { refreshToken } = refreshSchema.parse(req.body);
    const tokens = await authService.refresh(refreshToken);
    return res.json(tokens);
  } catch (err: any) {
    if (err.name === "ZodError") {
      return res.status(400).json({ message: "Invalid input", errors: err.errors });
    }
    if (["INVALID_REFRESH", "EXPIRED_REFRESH"].includes(err.message)) {
      return res.status(401).json({ message: "Invalid or expired refresh token" });
    }
    if (err.message === "INACTIVE") {
      return res.status(403).json({ message: "User account is inactive" });
    }
    // eslint-disable-next-line no-console
    console.error("refreshHandler error", err);
    return res.status(500).json({ message: "Internal server error" });
  }
}


