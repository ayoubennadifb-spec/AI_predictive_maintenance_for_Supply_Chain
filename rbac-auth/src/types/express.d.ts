import type { Role } from "@prisma/client";

declare global {
  namespace Express {
    // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
    interface UserPayload {
      userId: string;
      role: Role;
      isActive: boolean;
    }

    // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
    interface Request {
      user?: UserPayload;
    }
  }
}

export {};


