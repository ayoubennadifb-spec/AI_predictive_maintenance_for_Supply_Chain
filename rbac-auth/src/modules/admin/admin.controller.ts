import { Request, Response } from "express";
import { z } from "zod";
import { Role } from "@prisma/client";
import { userService } from "../users/user.service";

const createUserSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
  role: z.nativeEnum(Role).refine(
    (r) =>
      [Role.MANAGER, Role.LOGISTIQUE, Role.APPROVISIONNEUR].includes(r),
    { message: "Role must be MANAGER, LOGISTIQUE or APPROVISIONNEUR" },
  ),
});

const idParamSchema = z.object({
  id: z.string().uuid(),
});

const resetPasswordSchema = z.object({
  password: z.string().min(6),
});

export async function createUserHandler(req: Request, res: Response) {
  try {
    const dto = createUserSchema.parse(req.body);
    const user = await userService.createUser(dto);
    return res.status(201).json({
      id: user.id,
      email: user.email,
      role: user.role,
      isActive: user.isActive,
    });
  } catch (err: any) {
    if (err.name === "ZodError") {
      return res.status(400).json({ message: "Invalid input", errors: err.errors });
    }
    if (err.code === "P2002") {
      return res.status(409).json({ message: "Email already in use" });
    }
    // eslint-disable-next-line no-console
    console.error("createUserHandler error", err);
    return res.status(500).json({ message: "Internal server error" });
  }
}

export async function listUsersHandler(_req: Request, res: Response) {
  const users = await userService.listUsers();
  return res.json(users);
}

export async function activateUserHandler(req: Request, res: Response) {
  try {
    const { id } = idParamSchema.parse(req.params);
    const user = await userService.setActive(id, true);
    return res.json({
      id: user.id,
      email: user.email,
      role: user.role,
      isActive: user.isActive,
    });
  } catch (err: any) {
    if (err.name === "ZodError") {
      return res.status(400).json({ message: "Invalid id" });
    }
    if (err.code === "P2025") {
      return res.status(404).json({ message: "User not found" });
    }
    // eslint-disable-next-line no-console
    console.error("activateUserHandler error", err);
    return res.status(500).json({ message: "Internal server error" });
  }
}

export async function deactivateUserHandler(req: Request, res: Response) {
  try {
    const { id } = idParamSchema.parse(req.params);
    const user = await userService.setActive(id, false);
    return res.json({
      id: user.id,
      email: user.email,
      role: user.role,
      isActive: user.isActive,
    });
  } catch (err: any) {
    if (err.name === "ZodError") {
      return res.status(400).json({ message: "Invalid id" });
    }
    if (err.code === "P2025") {
      return res.status(404).json({ message: "User not found" });
    }
    // eslint-disable-next-line no-console
    console.error("deactivateUserHandler error", err);
    return res.status(500).json({ message: "Internal server error" });
  }
}

export async function resetPasswordHandler(req: Request, res: Response) {
  try {
    const { id } = idParamSchema.parse(req.params);
    const { password } = resetPasswordSchema.parse(req.body);
    const user = await userService.resetPassword(id, password);
    return res.json({
      id: user.id,
      email: user.email,
      role: user.role,
      isActive: user.isActive,
    });
  } catch (err: any) {
    if (err.name === "ZodError") {
      return res.status(400).json({ message: "Invalid input" });
    }
    if (err.code === "P2025") {
      return res.status(404).json({ message: "User not found" });
    }
    // eslint-disable-next-line no-console
    console.error("resetPasswordHandler error", err);
    return res.status(500).json({ message: "Internal server error" });
  }
}


