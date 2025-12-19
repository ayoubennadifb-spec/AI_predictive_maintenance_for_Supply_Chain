import { prisma } from "../../prisma";
import { Role } from "@prisma/client";
import bcrypt from "bcrypt";

export class UserService {
  async createUser(params: {
    email: string;
    password: string;
    role: Role;
  }) {
    const hashed = await bcrypt.hash(params.password, 10);
    return prisma.user.create({
      data: {
        email: params.email,
        password: hashed,
        role: params.role,
      },
    });
  }

  async listUsers() {
    return prisma.user.findMany({
      orderBy: { createdAt: "desc" },
      select: {
        id: true,
        email: true,
        role: true,
        isActive: true,
        createdAt: true,
        updatedAt: true,
      },
    });
  }

  async setActive(userId: string, isActive: boolean) {
    return prisma.user.update({
      where: { id: userId },
      data: { isActive },
    });
  }

  async resetPassword(userId: string, newPassword: string) {
    const hashed = await bcrypt.hash(newPassword, 10);
    return prisma.user.update({
      where: { id: userId },
      data: { password: hashed },
    });
  }
}

export const userService = new UserService();


