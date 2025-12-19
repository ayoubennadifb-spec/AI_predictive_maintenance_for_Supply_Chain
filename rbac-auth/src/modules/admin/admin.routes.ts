import { Router } from "express";
import {
  activateUserHandler,
  createUserHandler,
  deactivateUserHandler,
  listUsersHandler,
  resetPasswordHandler,
} from "./admin.controller";
import { authMiddleware } from "../../middleware/authMiddleware";
import { requireSuperAdmin } from "../../middleware/roleMiddleware";

export const adminRouter = Router();

// All admin routes require authentication and SUPER_ADMIN role
adminRouter.use(authMiddleware, requireSuperAdmin);

adminRouter.post("/users", createUserHandler);
adminRouter.get("/users", listUsersHandler);
adminRouter.patch("/users/:id/activate", activateUserHandler);
adminRouter.patch("/users/:id/deactivate", deactivateUserHandler);
adminRouter.patch("/users/:id/reset-password", resetPasswordHandler);


